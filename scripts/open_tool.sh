#!/usr/bin/env bash
set -euo pipefail

proton_command=waitforexitandrun
case "${1:-}" in
    launcher) executable=Launcher.exe ;;
    radiant)
        executable=CoDWaWRadiant.exe
        export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}d3dx9_37=n,b"
        ;;
    linker)
        executable=linker_pc.exe
        proton_command=runinprefix
        ;;
    converter)
        executable=converter.exe
        proton_command=runinprefix
        ;;
    *)
        printf 'Usage: %s {launcher|radiant|linker|converter} [args...]\n' "$0" >&2
        exit 2
        ;;
esac
shift

steam_root="${WAW_STEAM_ROOT:-$HOME/.local/share/Steam}"
dev_root="${WAW_DEV_ROOT:-$HOME/Games/waw-zombies-dev}"
proton="${WAW_PROTON:-$steam_root/steamapps/common/Proton - Experimental/proton}"

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$steam_root"
export STEAM_COMPAT_DATA_PATH="$dev_root/compatdata"
export STEAM_COMPAT_INSTALL_PATH="$dev_root/game"

cd "$STEAM_COMPAT_INSTALL_PATH/bin"
exec "$proton" "$proton_command" "$PWD/$executable" "$@"
