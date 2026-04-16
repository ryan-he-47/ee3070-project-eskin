# Arduino MIDI Workspace

This workspace contains the embedded instrument firmware, the AI continuation server, and the training/research code used to support them.
## What is here

- `eskin_project/`: ESP32-S3 firmware for a 16x16 pressure-sensing MIDI instrument.
## Main firmware flow

The instrument reads a 16x16 pressure matrix and converts it into MIDI events.
Supported outputs:

- USB MIDI
## AI continuation flow

The realtime continuation path is based on event tokens rather than frame-level piano roll data.
## Firmware entry points

- `eskin_project/eskin_project.ino`: main firmware entry
## AI continuation controls

In the current layout, the firmware uses CC102 for continuation control:
## Notes for upload

- Large generated datasets are ignored in git.
## Quick pointers

- Read `midi_gen_ai_rewrite/README.md` for generation and training details.

## Arduino dependency setup

This repository now ignores the local Arduino IDE `libraries/` folder.
Do not upload your machine-local library cache. Install required libraries with Arduino Library Manager instead.

Required external Arduino libraries for `eskin_project/`:

- ArduinoJson (by Benoit Blanchon)
	- Used by `eskin_project/src/wifi_tcp_client.h` (`#include <ArduinoJson.h>`)
- ESP32-BLE-MIDI (by lathoub)
	- Used by `eskin_project/src/BLEMidi.cpp` (`#include <BLEMIDI_Transport.h>`, `#include <hardware/BLEMIDI_ESP32.h>`)
- MIDI Library (by FortySevenEffects)
	- Required dependency of ESP32-BLE-MIDI (provides `MIDI.h` interface)

ESP32 core-provided components (no separate Library Manager install):

- WiFi / USB / USBMIDI / FreeRTOS / Wire / HardwareSerial

Recommended board package:

- Arduino ESP32 core by Espressif Systems (for ESP32-S3)
# An open-source MIDI instrument based on the integrated flexible PET film pressure-sensing matrix and ESP32

a repository for project design course ee3070, in cityuhk.



project overview: a multi-output programmable midi  instrument based on esp32 and 16\*16 pressure sensor grid.



functions: read a 16\*16 pressure data from uart serial port with data format "positionByte, dataByte", i.e., 4\_bit\_col\_num, 4\_bit\_row\_num, 8\_bit\_sensor\_pressure, and generate midi signal according to the pressure map.



features: 

support multiple output types, uart, BLE and usb(to be implemented).

programmable key layout(will have several good plug-and-play predefined configs).

easy to add more key trigger logics by inheritance of pressToMIDI class and override process() function.



requirements:

this project is write in Arduino ide, the default "libraries/" folder of our Arduino ide has been uploaded, u can merge it with your libraries folder or search for the libraries from Arduino library manager according to the library name.



p.s. early version, update function of class pressToMIDI() haven't been implemented, and cache function is ai written and haven't been tested, we are working on this. other functions in the main file and pressure\_process function block are hand written with comments.





file structure:





eskin\_project:.

│  config.ino 	//user's key config file(to be implemented)

│  eskin\_project.ino	//main .ino file (fully hand written, no ai)

│

└─src

&nbsp;       BLEMidi.cpp	

&nbsp;       BLEMidi.h		//Bluetooth LE function block header file

&nbsp;       FPGA\_Reader.cpp

&nbsp;       FPGA\_Reader.h		//UART serial port receive function block (name being "FPGA\_Reader" is because we use a fpga dev board to send uart)

&nbsp;       keyboard.cpp

&nbsp;       keyboard.h		//keyboard control function，uses 4*4 keyboard from emakefun (keyboard itself sometimes fail to work)

&nbsp;       pressure\_process.cpp

&nbsp;       pressure\_process.h		//core function block, generate midi event from raw pressure map (mostly hand written, some ai assist)







