# traktor-nml-utils is not packaged in nixpkgs; build from PyPI.
{
  lib,
  buildPythonPackage,
  fetchurl,
  setuptools,
  typer,
  xsdata,
}:

buildPythonPackage rec {
  pname = "traktor-nml-utils";
  version = "4.1.0";
  pyproject = true;

  # PyPI sdist uses underscored filename and hash-bucketed URL path.
  src = fetchurl {
    url = "https://files.pythonhosted.org/packages/15/64/3ff077ba741990fe26576f7dd809878ea6adbca606a3b2fbc7b918a2ac78/traktor_nml_utils-4.1.0.tar.gz";
    hash = "sha256-b5xOWGZRr+lsW7mgQu2H5njVAbWA5VUr+1O8QKq3jQM=";
  };

  build-system = [ setuptools ];

  dependencies = [
    typer
    xsdata
  ];

  # No tests shipped in the sdist.
  doCheck = false;

  meta = {
    description = "Utilities for working with Traktor NML files";
    homepage = "https://github.com/wolkenarchitekt/traktor-nml-utils";
    license = lib.licenses.gpl3Only;
  };
}
