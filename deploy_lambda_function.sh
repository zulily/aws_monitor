#!/usr/bin/env bash

. ./vars.sh

./package.sh

PYTHONPATH=./dist:$PYTHONPATH python deployscripts/setup_lambda.py
