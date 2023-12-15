#!/bin/bash

sudo lsof -t -i:9000 | xargs kill
alias get_esp8266='export PATH="/home/leiyong/workspace/ESP8266/esp-open-sdk/xtensa-lx106-elf/bin:$PATH"'
alias get_idf='. $HOME/workspace/ESP32/esp-idf/export.sh'
