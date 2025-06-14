#!/usr/bin/env sh
#
# Crude installation script for Unix-like systems
#
set -e

check_command() {
  command -v "$1" >/dev/null 2>&1
}

check_continue() {
  echo
  echo "$1 Continue? [Enter]"
  read -r yesno
  if [ "$yesno" = "" ] ; then
    return 0
  else
    echo "Installation Aborted"
    exit
  fi
}

check_yesno() {
  echo
  echo "$1 [y/n]"
  read -r yesno
  if [ "$yesno" = "y" ] ; then
    return 0
  else
    return 1
  fi
}

echo_continue() {
  echo "  - $1"
}

get_fonts() {
  if check_yesno "Download Tex-Gyre fonts from gust.org.pl?" ; then
    if check_command unzip ; then
      if check_command wget ; then
        mkdir -p "$HOME/.local/share/fonts"
        TMPF=$(mktemp -p . texgyreotf-XXXXXX)
        wget -nv --show-progress -O "$TMPF" https://www.gust.org.pl/projects/e-foundry/tex-gyre/whole/tg2_501otf.zip
        unzip -q -j -d "$HOME/.local/share/fonts" "$TMPF"
        fc-cache -f
        rm "$TMPF"
        echo_continue "Added Tex-Gyre Fonts"
      else
        check_continue "Missing wget, fonts not installed."
      fi
    else
      check_continue "Missing unzip, fonts not installed."
    fi
  else
    echo_continue "Skipped"
  fi
}

sysup_apt() {
  echo "Synchronize Package Index:"
  sudo apt-get update
  echo_continue "Done"

  echo "Install Required Packages:"
  sudo apt-get install -y python3-venv python3-pip python3-cairo python3-gi python3-gi-cairo python3-serial python3-paho-mqtt python3-dateutil python3-xlwt gir1.2-gtk-3.0 gir1.2-rsvg-2.0 gir1.2-pango-1.0
  echo_continue "Done"

  if check_yesno "Install optional fonts, evince, rsync and MQTT broker?" ; then
    if [ -e "/etc/mx-version" ] ; then
      sudo apt-get install -y fonts-texgyre fonts-noto evince rsync
      check_continue "MX detected: MQTT broker not installed."
    else
      sudo apt-get install -y fonts-texgyre fonts-noto evince mosquitto rsync
    fi
    echo_continue "Done"
  else
    echo_continue "Skipped"
  fi
}

sysup_dnf() {
  echo "Install Required Packages:"
  sudo dnf -q -y install gtk3 gobject-introspection cairo-gobject python3-pip python3-cairo python3-pyserial python3-paho-mqtt python3-dateutil python3-xlwt
  echo_continue "Done"

  if check_yesno "Install optional fonts, evince, rsync and MQTT broker?" ; then
    sudo dnf -q -y install google-noto-sans-fonts google-noto-mono-fonts google-noto-emoji-fonts texlive-tex-gyre evince rsync mosquitto
    sudo systemctl enable mosquitto.service
    echo_continue "Done"
  else
    echo_continue "Skipped"
  fi
}

sysup_pacman() {
  echo "Install Required Packages:"
  sudo pacman -S --noconfirm -q --needed python python-pip gtk3 python-pyserial python-dateutil python-xlwt python-paho-mqtt python-gobject python-cairo
  echo_continue "Done"

  if check_yesno "Install optional fonts, evince, rsync and MQTT broker?" ; then
    sudo pacman -S --noconfirm -q --needed noto-fonts tex-gyre-fonts evince rsync mosquitto
    sudo systemctl enable mosquitto.service
    echo_continue "Done"
  else
    echo_continue "Skipped"
  fi
}

sysup_apk() {
  echo "Install Required Packages:"
  sudo apk add py3-pip py3-pyserial py3-dateutil py3-paho-mqtt py3-gobject3 py3-cairo 
  echo_continue "Done"

  if check_yesno "Install optional fonts, evince, rsync and MQTT broker?" ; then
    sudo apk add font-noto evince rsync mosquitto
    echo_continue "Packages"
    sudo rc-update add mosquitto default
    sudo rc-service mosquitto start
    echo_continue "Started MQTT Broker"
  else
    echo_continue "Skipped"
  fi
}

sysup_emerge() {
  echo "Install Packages:"
  sudo emerge --ask -n dev-libs/gobject-introspection dev-python/pygobject dev-python/python-dateutil dev-python/xlwt dev-python/pyserial dev-python/paho-mqtt media-fonts/tex-gyre media-fonts/noto app-text/evince app-misc/mosquitto net-misc/rsync
  echo_continue "Done"
}

sysup_pkg() {
  echo "Install Packages:"
  sudo pkg install wget unzip evince rsync mosquitto
  echo_continue "Done"
}

# abort if not normal user
if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root, installation aborted."
  exit
fi

# ensure write access to wd
cd /tmp

# check operating system
WSL=""
if [ -n "$WSL_DISTRO_NAME" ] ; then
  echo "Detected Windows Subsystem for Linux"
  WSL=" (WSL)"
fi
echo "Operating System:"
OSINFO="unknown"
if check_command uname ; then
  OSINFO=$(uname -o)
fi
if [ "$OSINFO" = "unknown" ] ; then
  check_continue "Unknown OS${WSL}."
else
  echo_continue "$OSINFO$WSL"
fi

# check distribution via os-release if available
PYTHON=python3
ttygroup="unknown"
pkgstyle="unknown"
getfonts="no"
if [ -e /etc/os-release ] ; then
  # This machine probably uses systemd, check distro and version
  . /etc/os-release
  echo "Distribution/Release:"
  dv=$(echo "$VERSION_ID" | cut -d . -f 1)
  case "$ID" in
    "debian")
      pkgstyle="apt"
      ttygroup="dialout"
      if [ "$dv" -gt 10 ] ; then
        echo_continue "$NAME $VERSION"
      else
        check_continue "$NAME $VERSION not supported."
      fi
    ;;
    "ubuntu")
      pkgstyle="apt"
      ttygroup="dialout"
      echo_continue "$NAME $VERSION"
    ;;
    "linuxmint")
      pkgstyle="apt"
      ttygroup="dialout"
      echo_continue "$NAME $VERSION"
    ;;
    "arch")
      pkgstyle="pacman"
      ttygroup="uucp"
      echo_continue "$NAME"
    ;;
    "manjaro")
      pkgstyle="pacman"
      ttygroup="uucp"
      echo_continue "$NAME"
    ;;
    "alpine")
      pkgstyle="apk"
      ttygroup="dialout"
      getfonts="yes"
      echo_continue "$NAME $VERSION_ID"
    ;;
    "fedora")
      pkgstyle="dnf"
      ttygroup="dialout"
      echo_continue "$NAME $VERSION"
    ;;
    "gentoo")
      pkgstyle="emerge"
      ttygroup="dialout"
      echo_continue "$NAME $VERSION_ID"
    ;;
    "slackware")
      pkgstyle="none"
      ttygroup="dialout"
      getfonts="yes"
      echo_continue "$NAME $VERSION"
    ;;
    "freebsd")
      pkgstyle="pkg"
      ttygroup="dialer"
      getfonts="yes"
      PYTHON=python3.11
      echo_continue "$NAME $VERSION"
    ;;
    "msys2")
      echo_continue "$NAME not supported by this installer."
      exit
    ;;
    *)
      check_continue "$NAME $VERSION not recognised."
    ;;
  esac
fi

echo "Package Manager:"
if [ "$pkgstyle" = "unknown" ] ; then
  if check_command apt ; then
    pkgstyle="apt"
    echo_continue "Debian/apt"
  elif command -v pacman ; then
    pkgstyle="pacman"
    echo_continue "Arch/pacman"
  elif command -v dnf ; then
    pkgstyle="dnf"
    echo "Fedora/dnf"
  elif command -v apk ; then
    pkgstyle="apk"
    echo_continue "Alpine/apk"
  elif command -v brew ; then
    pkgstyle="brew"
    check_continue "MacOS/brew todo."
  elif command -v flatpak ; then
    pkgstyle="flatpak"
    check_continue "Flatpak todo."
  else
    check_continue "Not found."
  fi
else
  echo_continue "$pkgstyle"
fi

if [ "$pkgstyle" = "unknown" ] ; then
  # assume ok
  true
elif [ "$pkgstyle" = "none" ] ; then
  # skipped by os-release
  true
else
  if check_yesno "Use $pkgstyle to install requirements?" ; then
    # Don't update packages if sudo not available
    if check_command sudo ; then
      case "$pkgstyle" in
        "apt")
          sysup_apt
        ;;
        "dnf")
          sysup_dnf
        ;;
        "apk")
          sysup_apk
        ;;
        "pkg")
          sysup_pkg
        ;;
        "pacman")
          sysup_pacman
        ;;
        "emerge")
          sysup_emerge
        ;;
        *)
          echo_continue "Unknown package style - skipped"
        ;;
      esac
    else
      check_continue "sudo not available, install packages skipped."
    fi
  fi
fi

# check serial port access
if [ "$ttygroup" = "unknown" ] ; then
  true
else
  if groups | grep -F "$ttygroup" >/dev/null 2>&1 ; then
    echo "Serial Port Access:"
    echo_continue "OK ($ttygroup)"
  else
    if check_command sudo ; then
      if check_yesno "Add $USER to group $ttygroup for serial port access?" ; then
        if [ "$pkgstyle" = "pkg" ] ; then
          sudo pw group mod -n "$ttygroup" -m "$USER"
        else
          sudo gpasswd -a "$USER" "$ttygroup"
        fi
        echo_continue "Done"
      else
        echo_continue "Skipped"
      fi
    else
      check_continue "Add user to group $ttygroup to access serial port."
    fi
  fi
fi

# if tex gyre not packaged, fetch with wget
if [ "$getfonts" = "yes" ] ; then
  get_fonts
fi

# check python interpreter version
echo "Python Interpreter:"
if check_command "$PYTHON" ; then
  echo_continue "Present"
else
  echo_continue "Python interpreter not found, installation aborted."
  exit
fi
echo "Python Version >= 3.11:"
if $PYTHON -c 'import sys
print(sys.version_info>=(3,11))' | grep -F "True" >/dev/null ; then
  echo_continue "Yes"
else
  echo_continue "Python version too old, installation aborted."
  exit
fi

# check for venv module
echo "Python venv Module:"
if $PYTHON -c 'import venv' >/dev/null 2>&1 ; then
  echo_continue "Present"
else
  echo_continue "Not available, installation aborted."
  exit
fi

# check working dir
DPATH="$HOME/Documents/metarace"
VDIR="venv"
VPATH="$DPATH/$VDIR"
echo "Check Installation Path:"
if [ -d "$VPATH" ] ; then
  echo_continue "Present"
else
  mkdir -p "$DPATH"
  echo_continue "Creating new venv $VPATH"
fi

# re-build venv
echo "Update Venv:"
$PYTHON -m venv --system-site-packages "$VPATH"
echo_continue "Done"

# install packages
echo "Update Applications From PyPI:"
if [ -e "$VPATH/bin/pip3" ] ; then 
  "$VPATH/bin/pip3" install metarace-roadmeet metarace-trackmeet metarace-tagreg metarace-ttstart --upgrade
  echo_continue "roadmeet, trackmeet, tagreg, ttstart"
else
  echo_continue "Unable to install: Virtual env not setup."
  exit
fi

# run a dummy metarace init to populate data directories
echo "Defaults folder:"
DEFICON="$DPATH/default/metarace_icon.svg"
if [ -e "$DEFICON" ] ; then
  echo_continue "Replacing application icon"
  rm "$DEFICON"
fi
"$VPATH/bin/python3" -c 'import metarace
import os
os.chdir(metarace.DATA_PATH)
metarace.init()'
echo_continue "Updating defaults"

# add desktop entries
echo "Desktop Shortcuts:"

# copy icon to shared folder if WSL detected
if [ -n "$WSL" ] ; then
  SHAREICON="/usr/share/icons/hicolor/scalable/apps/metarace.svg"
  sudo mkdir -p "/usr/share/icons/hicolor/scalable/apps"
  if [ -e "$SHAREICON" ] ; then
    sudo rm "$SHAREICON"
  fi
  sudo cp "$DEFICON" "$SHAREICON"
  DEFICON="metarace"
  echo_continue "Install shared icon"
fi

XDGPATH="$HOME/.local/share/applications"
SPATH="$XDGPATH/metarace"
mkdir -p "$SPATH"

# Roadmeet
TMPF=$(mktemp -p "$SPATH")
tee "$TMPF" <<__EOF__ >/dev/null
[Desktop Entry]
Name=Roadmeet
Comment=Timing and results for road cycling meets
Keywords=cycling;road cycling;results;timing;
Exec=$VPATH/bin/roadmeet %U
Icon=$DEFICON
Terminal=false
StartupNotify=true
Type=Application
Categories=Utility;GTK;Sports;
MimeType=inode/directory;
Actions=create;edit-default;

[Desktop Action create]
Name=Create New
Exec=$VPATH/bin/roadmeet --create

[Desktop Action edit-default]
Name=Edit Defaults
Exec=$VPATH/bin/roadmeet --edit-default
__EOF__
mv "$TMPF" "$SPATH/roadmeet.desktop"
echo_continue "Added roadmeet.desktop"

# Trackmeet
TMPF=$(mktemp -p "$SPATH")
tee "$TMPF" <<__EOF__ >/dev/null
[Desktop Entry]
Name=Trackmeet
Comment=Timing and results for track cycling meets
Keywords=cycling;track cycling;velodrome;results;timing;
Exec=$VPATH/bin/trackmeet %U
Icon=$DEFICON
Terminal=false
StartupNotify=true
Type=Application
Categories=Utility;GTK;Sports;
MimeType=inode/directory;
Actions=create;edit-default;

[Desktop Action create]
Name=Create New
Exec=$VPATH/bin/trackmeet --create

[Desktop Action edit-default]
Name=Edit Defaults
Exec=$VPATH/bin/trackmeet --edit-default
__EOF__
mv "$TMPF" "$SPATH/trackmeet.desktop"
echo_continue "Added trackmeet.desktop"

# TT Start
TMPF=$(mktemp -p "$SPATH")
tee "$TMPF" <<__EOF__ >/dev/null
[Desktop Entry]
Type=Application
Exec=$VPATH/bin/ttstart
Icon=$DEFICON
Terminal=false
StartupNotify=true
Name=TT Start
Comment=Time trial start console
Categories=Utility;GTK;Sports;
__EOF__
mv "$TMPF" "$SPATH/ttstart.desktop"
echo_continue "Added ttstart.desktop"

# Tagreg
TMPF=$(mktemp -p "$SPATH")
tee "$TMPF" <<__EOF__ >/dev/null
[Desktop Entry]
Type=Application
Exec=$VPATH/bin/tagreg
Icon=$DEFICON
Terminal=false
StartupNotify=true
Name=Transponder Registration
Comment=Transponder registration tool
Categories=Utility;GTK;Sports;
__EOF__
mv "$TMPF" "$SPATH/tagreg.desktop"
echo_continue "Added tagreg.desktop"

# WSL wants: /usr/share/applications
if [ -n "$WSL" ] ; then
  sudo chown -R root:root "$SPATH"
  sudo chmod -R 0644 "$SPATH"
  for file in "$SPATH"/* ; do
      sudo mv "$file" "/usr/share/applications"
  done
  echo_continue "move desktop files to /usr/share/applications"
  sudo rmdir "$SPATH"
  if check_command update-desktop-database ; then
    sudo update-desktop-database -q
    echo_continue "Updated MIME types cache"
  else
    echo_continue "MIME types cache not updated"
  fi
else
  if check_command update-desktop-database ; then
    update-desktop-database -q "$XDGPATH"
    echo_continue "Updated MIME types cache"
  else
    echo_continue "MIME types cache not updated"
  fi
fi

echo
echo "Metarace packages installed."
