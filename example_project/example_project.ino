


#include "ass.h"
 
#define ESP_BAUDRATE 115200 



void setup() { 
  // initialize serial for debugging 
  Serial.begin(115200); 
  //Serial1.begin(ESP_BAUDRATE); 
  // initialize ESP module 
  //WiFi.init(&Serial1); 
  // initialize ThingSpeak
  //ThingSpeak.begin(client);
  //pinMode(2,INPUT_PULLUP);
} 
  
void loop()
{ 
  //connectWiFi();
  Serial.println("running main loop"); 
    //task 1
  //readPublicChannel();
    //task 2
  //writeMyChannel();
    //task 3
  //readMyChannel();
  Serial.println(dih);
  fuck("juicy pu$$y");
  counting(5); 
} 








