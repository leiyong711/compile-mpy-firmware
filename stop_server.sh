#!/bin/bash

sudo lsof -t -i:9000 | xargs kill