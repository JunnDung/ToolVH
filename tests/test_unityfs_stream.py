import gc
import json
import random
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lz4.block
from toolvh.formats import extract, rebuild
from toolvh.model import Entry, Project, FileRecord, digest, atomic_write
from toolvh.patching import export_patch, install_patch
from toolvh.scanner import scan
from toolvh.unityfs_stream import Bundle, UnsupportedVersion, extract_file, rebuild_file


def fixture(path, at_end=False):
    payload = b'ASSET'+random.Random(1).randbytes(1100000)
    chunks = [payload[i:i+131072] for i in range(0, len(payload), 131072)]
    packed = [lz4.block.compress(c, store_size=False) for c in chunks]
    info = bytes(16)+struct.pack('>I',len(chunks))
    info += b''.join(struct.pack('>IIH',len(c),len(p),3) for c,p in zip(chunks,packed))
    info += struct.pack('>I',2)+struct.pack('>QQI',0,5,4)+b'resources.assets\0'
    info += struct.pack('>QQI',5,len(payload)-5,0)+b'resources.resS\0'
    compressed = info if at_end else lz4.block.compress(info,store_size=False)
    signature = b'UnityFS\0'+struct.pack('>I',8)+b'5.x.x\0'+b'6000.3.15f1\0'
    flags = 0x2c0 if at_end else 0x243
    header = signature+struct.pack('>QIII',0,len(compressed),len(info),flags)
    header += bytes((-len(header))%16)
    body = b''.join(packed)
    if at_end:
        result = header+body+compressed
    else:
        prefix = header+compressed
        result = prefix+bytes((-len(prefix))%16)+body
    result = result[:len(signature)]+struct.pack('>Q',len(result))+result[len(signature)+8:]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(result)
    return payload


class PackedUnityTests(unittest.TestCase):
    def test_read_both_index_locations_and_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            for end in (False,True):
                p=Path(d)/'data.unity3d'
                original=fixture(p,end)
                b=Bundle(p)
                self.assertEqual(b.member(b.nodes[0]),b'ASSET')
                self.assertEqual(b.member(b.nodes[1]),original[5:])
                with self.assertRaises(InterruptedError):
                    b.member(b.nodes[1],lambda:True)

    def test_rebuild_preserves_compressed_resource_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.unity3d'; fixture(p)
            before=Bundle(p)
            e=Entry('id','data.unity3d',{'bundle_member':'resources.assets'},'Hello','',translation='Xin chào')
            with patch('toolvh.unity.rebuild_unity',return_value='Xin chào'.encode()):
                output=rebuild_file(p,[e])
            after=Bundle(output)
            self.assertEqual(after.member(after.nodes[0]),'Xin chào'.encode())
            self.assertEqual(after.member(after.nodes[1]),before.member(before.nodes[1]))
            with p.open('rb') as a, output.open('rb') as b:
                a.seek(before.data_start); b.seek(after.data_start)
                self.assertEqual(a.read(before.data_end-before.data_start),b.read(before.data_end-before.data_start))
            name=Path(output); del output; gc.collect()
            self.assertFalse(name.exists())

    def test_scanner_bypasses_whole_file_limit_but_not_asset_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Game_Data'/'data.unity3d'; fixture(p)
            # Whole bundle above 1 MB; resource is not read by the asset extractor.
            with patch('toolvh.unity.extract_unity',return_value=([],'')) as read:
                b=Bundle(p)
                project=scan(d,deep=True,max_mb=1)
                read.assert_called_once()
                self.assertEqual(read.call_args.args[0],b'ASSET')
                self.assertEqual(project.files[0].kind,'unityfs')
            with patch('toolvh.unity.extract_unity') as read:
                _,note=extract_file(p,'data.unity3d',max_mb=0)
                read.assert_not_called()
                self.assertIn('vượt giới hạn',note)

    def test_truncated_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.unity3d'; fixture(p)
            p.write_bytes(p.read_bytes()[:-10])
            with self.assertRaises(ValueError): Bundle(p)

    def test_language_vectors_translate_only_labelled_english_slot(self):
        source={'CURRENT_LANGUAGE':['Français','English',None], 'PLAY':['Jouer','PLAY',None]}
        entries=extract(json.dumps(source),'json','terms.json')
        self.assertEqual(len(entries),1)
        self.assertTrue(entries[0].enabled)
        self.assertEqual(entries[0].locator,{'path':['PLAY',1]})
        entries[0].translation='CHƠI'
        result=json.loads(rebuild(json.dumps(source),'json',entries))
        self.assertEqual(result,{'CURRENT_LANGUAGE':['Français','English',None], 'PLAY':['Jouer','CHƠI',None]})
        del source['CURRENT_LANGUAGE']
        self.assertFalse(any(e.enabled for e in extract(json.dumps(source),'json','terms.json')))

    def test_stream_export_install_restore_and_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p=root/'game'/'Game_Data'/'data.unity3d'; fixture(p)
            entry=Entry('id','Game_Data/data.unity3d',{'bundle_member':'resources.assets'},'Hello','',translation='Xin chào')
            project=Project(str(root/'game'),files=[FileRecord(entry.file,'unityfs',digest(p))],entries=[entry],preserve_names=False)
            original=digest(p)
            with patch('toolvh.unity.rebuild_unity',return_value='Xin chào'.encode()):
                export_patch(project,root/'patch')
            self.assertEqual(digest(p),original)
            self.assertEqual(install_patch(root/'patch',root/'game'),1)
            self.assertEqual(install_patch(root/'patch',root/'game'),0)
            self.assertEqual(install_patch(root/'patch',root/'game',restore=True),1)
            self.assertEqual(digest(p),original)
            with patch.object(type(p),'read_bytes',side_effect=AssertionError('must stream')):
                atomic_write(root/'copy',p)
                self.assertEqual(digest(root/'copy'),original)

    def test_old_small_bundle_keeps_existing_reader(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'Game_Data'/'data.unity3d'; fixture(p)
            with patch('toolvh.unityfs_stream.extract_file',side_effect=UnsupportedVersion('old')):
                with patch('toolvh.scanner.extract_unity',return_value=([],'')) as read:
                    project=scan(d,deep=True,max_mb=2)
                    read.assert_called_once()
                    self.assertEqual(project.files[0].kind,'unity')
                with patch('toolvh.scanner.extract_unity') as read:
                    project=scan(d,deep=True,max_mb=1)
                    read.assert_not_called()
                    self.assertIn('old',project.files[0].note)
