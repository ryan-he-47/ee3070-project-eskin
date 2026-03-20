#include "MPE_Manager.h"


void MPEManager::setAvaliableChannel( int end){
  for(int i=0;i<=15;i++){
    if(i<=end-1){
      noteList[i]=-1;
    }else{
      noteList[i];
    }
  }
  
}

bool MPEManager::assignChannel(MIDIEvent* event){
  if(event->MPEnote>=128){return false;}
  return false;
}