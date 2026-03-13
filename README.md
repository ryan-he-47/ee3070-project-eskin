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







