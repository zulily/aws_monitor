#!/usr/bin/env bash
mkdir -p dist
rm -rf dist/*
rm aws_monitor.zip

cp *.py dist
cp -R monitordefs dist
pip install -r requirements.txt -t dist

(cd dist && zip -r ../aws_monitor *)
