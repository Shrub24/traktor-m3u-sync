"""Performance blobs written by Engine DJ, shared by the Engine test modules."""

# From the home-forge Engine media library.
REAL_BEAT_DATA = bytes.fromhex(
    "0000008a789c7378dad1c000048e991b6626006946060860924adcb93b6aed87037ffe43c0332688c4"
    "7793590f4436653a3e82f2d100b9fa1818008abf297e"
)
REAL_QUICK_CUES = bytes.fromhex(
    "00000081789c636000030e86fd1f181080761c871531c1aeca0d1f181daebe6002090000228212f0"
)
_EMPTY_LOOP = "00" + "000000000000f0bf" * 2 + "0000" + "00000000"
REAL_LOOPS = bytes.fromhex("0800000000000000" + _EMPTY_LOOP * 8)
