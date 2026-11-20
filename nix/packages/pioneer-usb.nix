{
  lib,
  rustPlatform,
  perl,
}:
rustPlatform.buildRustPackage {
  pname = "pioneer-usb";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ../..;
    fileset = lib.fileset.unions [
      ../../pioneer-usb/Cargo.toml
      ../../pioneer-usb/Cargo.lock
      ../../pioneer-usb/src
      # The snapshot contract fixture shared with the Python tests.
      ../../tests/fixtures/snapshot.json
    ];
  };
  buildAndTestSubdir = "pioneer-usb";
  cargoRoot = "pioneer-usb";
  cargoLock = {
    lockFile = ../../pioneer-usb/Cargo.lock;
    outputHashes."rbl-analysis-1.10.0" = "sha256-uwevTD94eLfaDRfE3Ithe486oDt5yXvm8NHhXi4QJGg=";
  };
  # Vendored OpenSSL for SQLCipher.
  nativeBuildInputs = [ perl ];
  meta = {
    description = "Pioneer USB library writer for traktor-m3u-sync snapshots";
    license = lib.licenses.gpl3Plus;
    mainProgram = "pioneer-usb";
  };
}
