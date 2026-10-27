#include <darlingserver/fsevents-device.hpp>
#include <sys/socket.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <thread>
#include <chrono>
namespace F=DarlingServer::FSEvents;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"INTERNAL_JOURNAL_FAIL line=%d %s\n",__LINE__,#x);exit(1);}}while(0)
static int type(int fd,int timeout) {
 pollfd p{fd,POLLIN,0};int ready=poll(&p,1,timeout);CHECK(ready>=0);if(!ready)return -1;
 char bytes[4096];auto n=read(fd,bytes,sizeof(bytes));CHECK(n>=10);int result;memcpy(&result,bytes,4);return result;
}
static void file(const std::string& path){std::ofstream out(path);out<<"real user payload";CHECK(out.good());}
int main(int argc,char** argv) {
 char pattern[]="/tmp/linuxcode-internal-journal-XXXXXX";char* p=mkdtemp(pattern);CHECK(p);std::string root=p;
 for(unsigned i=0;i<8;i++)file(root+"/user-"+std::to_string(i));
 std::filesystem::create_directory(root+"/nested");file(root+"/nested/.darling-fsevents-id");
 std::vector<int8_t> actions(16);actions[1]=actions[3]=1;
 int control=F::openDevice({{root,"/"}},O_RDONLY);CHECK(control>=0);
 int stream=F::cloneDevice(control,actions,64);CHECK(stream>=0);
 uint64_t before=0;CHECK(F::journalCurrent(control,root,before)==0);
 if(argc>1&&!strcmp(argv[1],"--expect-internal-loss")) {
  CHECK(type(stream,2000)==999);
  puts("OLD_INTERNAL_JOURNAL_WRITES_TRIGGER_RAW_EVENTS_DROPPED");return 0;
 }
 CHECK(type(stream,500)==-1);
 for(unsigned i=0;i<8;i++){
  auto from=root+"/user-"+std::to_string(i),to=from+"-renamed";
  CHECK(rename(from.c_str(),to.c_str())==0);CHECK(type(stream,2000)==3);
  CHECK(unlink(to.c_str())==0);CHECK(type(stream,2000)==1);
 }
 CHECK(rename((root+"/nested/.darling-fsevents-id").c_str(),(root+"/nested/renamed").c_str())==0);CHECK(type(stream,2000)==3);
 CHECK(unlink((root+"/nested/renamed").c_str())==0);CHECK(type(stream,2000)==1);
 std::this_thread::sleep_for(std::chrono::milliseconds(250));uint64_t after=0;
 CHECK(F::journalCurrent(control,root,after)==0&&after>before);CHECK(type(stream,300)==-1);
 close(stream);close(control);
 /* The same basename remains a user file in a non-prefix root. */
 char other[]="/tmp/linuxcode-ordinary-journal-name-XXXXXX";p=mkdtemp(other);CHECK(p);std::string ordinary=p;file(ordinary+"/.darling-fsevents-id");
 control=F::openDevice({{ordinary,"/guest"}},O_RDONLY);CHECK(control>=0);stream=F::cloneDevice(control,actions,64);CHECK(stream>=0);
 CHECK(rename((ordinary+"/.darling-fsevents-id").c_str(),(ordinary+"/renamed").c_str())==0);CHECK(type(stream,2000)==3);
 close(stream);close(control);std::filesystem::remove_all(ordinary);
 puts("INTERNAL_JOURNAL_NO_RAW_SELF_NOTIFICATIONS_REAL_RENAME_DELETE_AND_USER_NAMES_OK");
}
