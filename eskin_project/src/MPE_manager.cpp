#include "MPE_Manager.h"


void MPEManager::setAvaliableChannel(int start, int end){
  for(int i=0;i<=15;i++){
    if((i<=end-1)&&(i>=start-1)){
      noteList[i]=-1;
    }else{
      noteList[i]=-2;
    }
  }
  
}

bool MPEManager::assignChannel(MIDIEvent* event){
  if(event->MPEnote>=128){return false;}
  
  if(event->type==MIDIEventType::NoteOn){
    for(int i=0;i<=15;i++){
      if(event->MPEnote==noteList[i]){return false;}
    }
  }

      
  for(int i=0;i<=15;i++){
    if((event->type==MIDIEventType::NoteOn)&&(noteList[i]==-1)){
      event->channel=i+1;
      noteList[i]=event->MPEnote;
      return true;
    }
    if((event->type==MIDIEventType::NoteOff)&&(noteList[i]==event->MPEnote)){
      event->channel=i+1;
      noteList[i]=-1;
      return true;
    }
    if(noteList[i]==event->MPEnote){
      event->channel=i+1;
      return true;
    }
  }
  return false;
}

