#!/bin/bash
HERE=$(dirname $0)

# Pull in changes from a built version of malcolmjs
RELEASE=https://github.com/DiamondLightSource/malcolmjs/releases/download/1.7.12/malcolmjs-1.7.12-0-g4e5e25f.tar.gz
TMP=/tmp/malcolmjs.tar.gz

git rm -rf $HERE/www
rm -rf $HERE/www
mkdir $HERE/www
wget -O $TMP $RELEASE
tar -C $HERE/www -zxf $TMP
git add $HERE/www

