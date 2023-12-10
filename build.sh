#!/usr/bin/env sh

MAINFILENAME=binary-waterfall
ENVNAME=$MAINFILENAME

ORIGDIR=$PWD
DISTDIR=$ORIGDIR/dist
BUILDDIR=$ORIGDIR/build

PY=$ORIGDIR/$MAINFILENAME.py
SPEC=$ORIGDIR/$MAINFILENAME.spec
EXE=$DISTDIR/$MAINFILENAME

VERSION_INFO=$ORIGDIR/file_version_info.txt


echo 'Building portable executable...'
conda run -n $ENVNAME create-version-file version.yml --outfile $VERSION_INFO || exit 1 # abort script on failure
conda run -n $ENVNAME pyinstaller \
    --clean \
    --noconfirm \
    --noconsole \
	--add-data resources:resources/ \
    --add-data version.yml:. \
    --add-data icon.png:. \
    --onefile \
    --icon=icon.ico \
    --version-file=$VERSION_INFO \
    "$PY"


echo Cleaning up before making release...
mv $EXE $ORIGDIR
rm -rf "$DISTDIR" "$BUILDDIR" "$SPEC" "$VERSION_INFO"
