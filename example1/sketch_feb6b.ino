#include <Arduino.h>
#include "WiFiEsp.h" 
#include "ThingSpeak.h"
char ssid[] = "REDMI K80 U"; // your network SSID (name) 
char pass[] = "88888888"; // your network password 
int status = WL_IDLE_STATUS; // the Wifi radio's status 
WiFiEspClient  client;



void connectWiFi(){
  if(WiFi.status() != WL_CONNECTED){ 
    Serial.print("Attempting to connect to SSID: "); 
    Serial.println(ssid); 
    while(WiFi.status() != WL_CONNECTED){ 
      WiFi.begin(ssid, pass); // Connect to WPA/WPA2 network 
       
    }
    Serial.println("\nConnected"); 
  }
}
void printWifiData()
{ 
  // print your WiFi shield's IP address 
  IPAddress ip = WiFi.localIP(); 
  Serial.print("IP Address: "); 
  Serial.println(ip); 
 
}

void counting(int seconds){
  Serial.print("wait ");
  Serial.print(seconds);
  Serial.print(" seconds, counting...");
  for(int i=0 ; i<seconds ; i++){
    Serial.print(" ");Serial.print(i+1);Serial.print("/");Serial.print(seconds);Serial.print(" ");
    delay(1000);
  }
  Serial.println("");
  Serial.println("Done");
}

void readPublicChannel(){
  //task 1
  Serial.println("start reading :channel 1785844, field2");
  float x = ThingSpeak.readFloatField(1785844,2);
  int readStatus=ThingSpeak.getLastReadStatus();
  if(readStatus==200){
    Serial.print("read finished, result is: ");
    Serial.println(x);
  }else{
    Serial.println("read failed!");
  }
  
}

void writeMyChannel(){
  //task 2
  for(int i=0 ; i<5 ; i++){
    float value1=random(1,100)/100.0;
    float value2=random(1,100)/100.0;
    ThingSpeak.setField(1,(i+value1));
    ThingSpeak.setField(2,(i+value2));
    Serial.print("wrinting: ");Serial.print(i+value1);Serial.print(" to field 1, ");Serial.print(i+value2);Serial.print("to field2.");Serial.println();
    ThingSpeak.writeFields(3253751,"QAV763QJ1P1FALXZ");
    counting(16);
  }
  
  while(true){
    Serial.println("program paused");
    delay(10000);
  }
}

void readMyChannel(){
  //task 3
  int time = 0;
  while(true){
    
    if (digitalRead(2) == LOW){
      time++;
      delay(1);
    }
    if (digitalRead(2) == HIGH && (time>0)){
      time--;
      delay(1);
    }
    if (time>100){
      time=0;
      Serial.println("pressed,now reading from channel 3253751, field1...");
      float data=ThingSpeak.readFloatField(3253751,1,"0STSU9HXWLB5XVBB");
      String timeStamp=ThingSpeak.readCreatedAt(3253751,"0STSU9HXWLB5XVBB");
      Serial.print("value is: ");
      Serial.print(data);
      Serial.print(", created at: ");
      Serial.println(timeStamp);
      break;

    }

  }
  
}
/*
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
*/