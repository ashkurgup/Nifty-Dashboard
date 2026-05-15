{pkgs}: {
  deps = [
    pkgs.nss
    pkgs.nspr
    pkgs.chromium
    pkgs.redis
  ];
}
