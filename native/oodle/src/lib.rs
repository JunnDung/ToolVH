//! Narrow ABI for the MIT oozextract decoder. Each call runs in a fresh WASM store.
use oozextract::Extractor;

const LIMIT: usize = 64 * 1024 * 1024;

#[no_mangle]
pub extern "C" fn allocate(length: usize) -> *mut u8 {
    if length == 0 || length > LIMIT {
        return std::ptr::null_mut();
    }
    let mut buffer = vec![0u8; length];
    let pointer = buffer.as_mut_ptr();
    std::mem::forget(buffer);
    pointer
}

/// Pointers are allocated by this module and supplied by the bounded host wrapper.
#[no_mangle]
pub unsafe extern "C" fn decode(input: *const u8, input_len: usize, output: *mut u8, output_len: usize) -> usize {
    if input.is_null() || output.is_null() || input_len == 0 || output_len == 0
        || input_len > LIMIT || output_len > LIMIT {
        return 0;
    }
    let source = std::slice::from_raw_parts(input, input_len);
    let target = std::slice::from_raw_parts_mut(output, output_len);
    Extractor::new().read_from_slice(source, target).unwrap_or(0)
}
