#include <darlingserver/file-signatures.hpp>
#include <darlingserver/apple-code-signing-roots.hpp>
#include <openssl/cms.h>
#include <openssl/err.h>
#include <openssl/pem.h>
#include <openssl/x509v3.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <climits>
#include <cstring>
#include <fcntl.h>
#include <map>
#include <memory>
#include <mutex>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace DarlingServer::FileSignatures {
namespace {
uint32_t be32(const unsigned char* p) { return uint32_t(p[0])<<24 | uint32_t(p[1])<<16 | uint32_t(p[2])<<8 | p[3]; }
uint64_t be64(const unsigned char* p) { return uint64_t(be32(p))<<32 | be32(p+4); }
uint32_t le32(const unsigned char* p) { return uint32_t(p[3])<<24 | uint32_t(p[2])<<16 | uint32_t(p[1])<<8 | p[0]; }
bool range(uint64_t offset,uint64_t size,uint64_t limit) { return offset<=limit && size<=limit-offset && offset<=INT64_MAX && size<=uint64_t(INT64_MAX)-offset; }
bool readAt(int fd,void* data,size_t size,uint64_t offset,uint64_t limit) {
    if (!range(offset,size,limit)) return false;
    auto* p=static_cast<unsigned char*>(data);
    while (size) {
        ssize_t n=pread(fd,p,size,static_cast<off_t>(offset));
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return false;
        p+=n;offset+=n;size-=n;
    }
    return true;
}
bool sameFile(const struct stat& a,const struct stat& b) {
    return a.st_dev==b.st_dev && a.st_ino==b.st_ino && a.st_size==b.st_size &&
        a.st_mtim.tv_sec==b.st_mtim.tv_sec && a.st_mtim.tv_nsec==b.st_mtim.tv_nsec &&
        a.st_ctim.tv_sec==b.st_ctim.tv_sec && a.st_ctim.tv_nsec==b.st_ctim.tv_nsec;
}
struct Certs { STACK_OF(X509)* value=nullptr;~Certs(){sk_X509_pop_free(value,X509_free);} };
bool strongKey(X509* cert) {
    EVP_PKEY* key=X509_get0_pubkey(cert);if (!key) return false;
    int type=EVP_PKEY_base_id(key),bits=EVP_PKEY_bits(key);
    return ((type==EVP_PKEY_RSA || type==EVP_PKEY_RSA_PSS) && bits>=2048) || (type==EVP_PKEY_EC && bits>=256);
}
bool codeSigningLeaf(X509* leaf) {
    std::unique_ptr<EXTENDED_KEY_USAGE,decltype(&EXTENDED_KEY_USAGE_free)> eku(
        static_cast<EXTENDED_KEY_USAGE*>(X509_get_ext_d2i(leaf,NID_ext_key_usage,nullptr,nullptr)),EXTENDED_KEY_USAGE_free);
    if (!eku) return false;
    for (int i=0;i<sk_ASN1_OBJECT_num(eku.get());++i)
        if (OBJ_obj2nid(sk_ASN1_OBJECT_value(eku.get(),i))==NID_code_sign) return strongKey(leaf);
    return false;
}
bool softwareLeaf(X509* leaf) {
    std::unique_ptr<ASN1_OBJECT,decltype(&ASN1_OBJECT_free)> marker(OBJ_txt2obj("1.2.840.113635.100.6.22",1),ASN1_OBJECT_free);
    int at=X509_get_ext_by_OBJ(leaf,marker.get(),-1);
    return at>=0 && X509_get_ext_by_OBJ(leaf,marker.get(),at)<0 && codeSigningLeaf(leaf);
}
int verifyKnownAppleCriticalExtension(int ok,X509_STORE_CTX* ctx) {
    if(ok || X509_STORE_CTX_get_error(ctx)!=X509_V_ERR_UNHANDLED_CRITICAL_EXTENSION)return ok;
    // OpenSSL does not know Apple's Developer ID Application certificate
    // marker. Recognize exactly that leaf marker, whose value must be DER NULL;
    // leave every other unknown critical extension as a verification failure.
    if(X509_STORE_CTX_get_error_depth(ctx)!=0)return 0;
    X509* cert=X509_STORE_CTX_get_current_cert(ctx);bool found=false;
    for(int i=0;i<X509_get_ext_count(cert);++i) {
        X509_EXTENSION* ext=X509_get_ext(cert,i);
        if(!X509_EXTENSION_get_critical(ext) || X509_supported_extension(ext))continue;
        char oid[100]={};OBJ_obj2txt(oid,sizeof(oid),X509_EXTENSION_get_object(ext),1);
        const ASN1_OCTET_STRING* data=X509_EXTENSION_get_data(ext);
        if(found || std::strcmp(oid,"1.2.840.113635.100.6.1.13") ||
            ASN1_STRING_length(data)!=2 || std::memcmp(ASN1_STRING_get0_data(data),"\x05\x00",2))return 0;
        found=true;
    }
    if(!found || !codeSigningLeaf(cert))return 0;
    X509_STORE_CTX_set_error(ctx,X509_V_OK);return 1;
}
bool verifyCMS(const unsigned char* encoded,size_t size,const unsigned char* directory,size_t directorySize,bool platformOnly) {
    if (size>LONG_MAX || directorySize>INT_MAX) return false;
    const unsigned char* cursor=encoded;
    std::unique_ptr<CMS_ContentInfo,decltype(&CMS_ContentInfo_free)> cms(d2i_CMS_ContentInfo(nullptr,&cursor,size),CMS_ContentInfo_free);
    if (!cms || cursor!=encoded+size || OBJ_obj2nid(CMS_get0_type(cms.get()))!=NID_pkcs7_signed) return false;
    auto* signers=CMS_get0_SignerInfos(cms.get());if (!signers || sk_CMS_SignerInfo_num(signers)!=1) return false;
    auto content=CMS_get0_content(cms.get());if (!content || *content) return false;
    std::unique_ptr<X509_STORE,decltype(&X509_STORE_free)> store(X509_STORE_new(),X509_STORE_free);
    std::unique_ptr<BIO,decltype(&BIO_free)> roots(BIO_new_mem_buf(appleCodeSigningRoots,sizeof(appleCodeSigningRoots)-1),BIO_free);
    if (!store || !roots) return false;
    unsigned added=0;
    while (X509* root=PEM_read_bio_X509(roots.get(),nullptr,nullptr,nullptr)) {
        int ok=X509_STORE_add_cert(store.get(),root);X509_free(root);if (ok!=1) return false;++added;
    }
    ERR_clear_error();if (added!=3) return false;
    // Apple Software Signing uses Basic X.509 without temporal validity, as
    // documented in SecPolicyPriv.h and SecPolicyCreateAppleSoftwareSigning.
    // Anchor, CMS signature, issuer, leaf marker, EKU and key checks remain.
    if (!X509_STORE_set_flags(store.get(),X509_V_FLAG_NO_CHECK_TIME) ||
        !X509_STORE_set_purpose(store.get(),X509_PURPOSE_ANY)) return false;
    if(!platformOnly)X509_STORE_set_verify_cb(store.get(),verifyKnownAppleCriticalExtension);
    std::unique_ptr<BIO,decltype(&BIO_free)> data(BIO_new_mem_buf(directory,directorySize),BIO_free);
    std::unique_ptr<BIO,decltype(&BIO_free)> sink(BIO_new(BIO_s_null()),BIO_free);
    if (!data || !sink || CMS_verify(cms.get(),nullptr,store.get(),data.get(),sink.get(),CMS_BINARY)!=1) return false;
    X509* leaf=nullptr;CMS_SignerInfo_get0_algs(sk_CMS_SignerInfo_value(signers,0),nullptr,&leaf,nullptr,nullptr);
    if (!leaf || !(platformOnly?softwareLeaf(leaf):codeSigningLeaf(leaf))) return false;
    Certs certificates;certificates.value=CMS_get1_certs(cms.get());
    std::unique_ptr<X509_STORE_CTX,decltype(&X509_STORE_CTX_free)> ctx(X509_STORE_CTX_new(),X509_STORE_CTX_free);
    if (!ctx || X509_STORE_CTX_init(ctx.get(),store.get(),leaf,certificates.value)!=1 || X509_verify_cert(ctx.get())!=1) return false;
    auto* chain=X509_STORE_CTX_get0_chain(ctx.get());
    int chainSize=sk_X509_num(chain);if(chainSize<2 || chainSize>5) return false;
    for(int i=0;i<chainSize;++i)if(!strongKey(sk_X509_value(chain,i)))return false;
    if(!platformOnly)return true;
    if(chainSize!=3)return false;
    X509* intermediate=sk_X509_value(chain,1);char name[128]={};
    constexpr char required[]="Apple Code Signing Certification Authority";
    int n=X509_NAME_get_text_by_NID(X509_get_subject_name(intermediate),NID_commonName,name,sizeof(name));
    return n==sizeof(required)-1 && std::memcmp(name,required,sizeof(required)-1)==0 && strongKey(intermediate);
}
struct Blob { const unsigned char* bytes=nullptr;size_t size=0; };
struct Registered {
    int fd=-1;struct stat identity{};uint64_t slice=0,covered=0;std::vector<unsigned char> directory;
    ~Registered(){if(fd>=0)close(fd);}
};
std::mutex registrationLock;
std::vector<std::unique_ptr<Registered>> registrations;
int failure(int error,const char* text,std::string* reason) { if(reason)*reason=text;return error; }
int verify(int fd,uint64_t slice,uint64_t signatureOffset,uint64_t signatureSize,uint64_t& covered,std::string* reason,bool platformOnly) {
    covered=0;struct stat before{};
    if (fstat(fd,&before)) return failure(errno,"descriptor stat failed",reason);
    if (!S_ISREG(before.st_mode)) return failure(EBADF,"descriptor is not a regular file",reason);
    if (before.st_size<32 || !range(slice,32,before.st_size) || signatureSize<12 || signatureSize>40*1024*1024)
        return failure(EINVAL,"signature input bounds",reason);
    std::array<unsigned char,32> header{};
    if (!readAt(fd,header.data(),header.size(),slice,before.st_size)) return failure(EINVAL,"Mach-O header read",reason);
    if (le32(header.data())!=0xfeedfacf || le32(header.data()+4)!=0x01000007)
        return failure(ENOEXEC,"expected Intel 64-bit Mach-O",reason);
    uint32_t ncmds=le32(header.data()+16),sizeofcmds=le32(header.data()+20);
    if (!ncmds || ncmds>16384 || sizeofcmds>16*1024*1024 || !range(slice+32,sizeofcmds,before.st_size))
        return failure(EINVAL,"Mach-O load command bounds",reason);
    std::vector<unsigned char> commands(sizeofcmds);
    if (!readAt(fd,commands.data(),commands.size(),slice+32,before.st_size)) return failure(EINVAL,"load command read",reason);
    size_t at=0;bool found=false;
    for (uint32_t i=0;i<ncmds;++i) {
        if (at>commands.size() || commands.size()-at<8) return failure(EINVAL,"truncated load command",reason);
        uint32_t kind=le32(commands.data()+at),size=le32(commands.data()+at+4);
        if (size<8 || size>commands.size()-at) return failure(EINVAL,"invalid load command size",reason);
        if (kind==0x1d) {
            if (found || size!=16 || le32(commands.data()+at+8)!=signatureOffset || le32(commands.data()+at+12)!=signatureSize)
                return failure(EINVAL,"signature range does not match Mach-O",reason);
            found=true;
        }
        at+=size;
    }
    if (at!=commands.size() || !found || slice>uint64_t(INT64_MAX)-signatureOffset ||
        !range(slice+signatureOffset,signatureSize,before.st_size)) return failure(EINVAL,"signature file bounds",reason);
    std::vector<unsigned char> signature(signatureSize);
    if (!readAt(fd,signature.data(),signature.size(),slice+signatureOffset,before.st_size)) return failure(EINVAL,"signature blob read",reason);
    if (be32(signature.data())!=0xfade0cc0) return failure(EPERM,"not an embedded signature",reason);
    uint32_t length=be32(signature.data()+4),count=be32(signature.data()+8);
    if (length<12 || length>signature.size() || count>(length-12)/8) return failure(EINVAL,"superblob bounds",reason);
    std::map<uint32_t,Blob> blobs;std::vector<std::pair<uint32_t,uint32_t>> ranges;
    for (uint32_t i=0;i<count;++i) {
        uint32_t kind=be32(signature.data()+12+8*i),offset=be32(signature.data()+16+8*i);
        if (offset<12+uint64_t(count)*8 || offset>length || length-offset<8) return failure(EINVAL,"superblob index bounds",reason);
        uint32_t size=be32(signature.data()+offset+4);
        if (size<8 || size>length-offset || blobs.count(kind)) return failure(EINVAL,"duplicate or truncated signature slot",reason);
        for (auto pair:ranges) if (offset<pair.second && pair.first<uint64_t(offset)+size) return failure(EINVAL,"overlapping signature blobs",reason);
        ranges.emplace_back(offset,offset+size);blobs.emplace(kind,Blob{signature.data()+offset,size});
        if (kind>=0x1000 && kind<0x1005) return failure(ENOTSUP,"alternate CodeDirectory not implemented",reason);
    }
    auto cdEntry=blobs.find(0),cmsEntry=blobs.find(0x10000);
    if (cdEntry==blobs.end()) return failure(EPERM,"CodeDirectory required",reason);
    Blob cd=cdEntry->second;
    if (cd.size<44 || be32(cd.bytes)!=0xfade0c02) return failure(EPERM,"invalid CodeDirectory slot",reason);
    uint32_t version=be32(cd.bytes+8),flags=be32(cd.bytes+12),hashOffset=be32(cd.bytes+16),ident=be32(cd.bytes+20);
    uint32_t special=be32(cd.bytes+24),slots=be32(cd.bytes+28);uint64_t limit=be32(cd.bytes+32);
    unsigned hashSize=cd.bytes[36],hashType=cd.bytes[37],pagePower=cd.bytes[39];
    bool adHoc=(flags&2)!=0;
    bool emptyCMS=cmsEntry!=blobs.end() && cmsEntry->second.size==8 && be32(cmsEntry->second.bytes)==0xfade0b01;
    if (adHoc && (platformOnly || (cmsEntry!=blobs.end() && !emptyCMS)))return failure(EPERM,"ad-hoc signature cannot establish Apple platform identity",reason);
    if (!adHoc && (cmsEntry==blobs.end() || be32(cmsEntry->second.bytes)!=0xfade0b01))return failure(EPERM,"CMS signature required",reason);
    if (version<0x20001 || version>0x20600 || pagePower>20 || !pagePower ||
        ident<44 || ident>=cd.size || !std::memchr(cd.bytes+ident,0,cd.size-ident)) return failure(EPERM,"unsupported CodeDirectory",reason);
    if (version>=0x20100 && (cd.size<48 || be32(cd.bytes+44))) return failure(ENOTSUP,"scatter CodeDirectory not implemented",reason);
    if (version>=0x20300 && !limit) { if(cd.size<64)return failure(EINVAL,"short CodeDirectory",reason);limit=be64(cd.bytes+56); }
    const EVP_MD* digest=hashType==1?EVP_sha1():(hashType==2||hashType==3)?EVP_sha256():hashType==4?EVP_sha384():nullptr;
    if (!digest || hashSize!=(hashType==3?20:unsigned(EVP_MD_size(digest)))) return failure(ENOTSUP,"unsupported CodeDirectory digest",reason);
    uint64_t pageSize=uint64_t(1)<<pagePower;
    if (!limit || limit!=signatureOffset || limit>uint64_t(before.st_size)-slice ||
        slots!=(limit+pageSize-1)/pageSize || hashOffset>cd.size ||
        uint64_t(slots)*hashSize>cd.size-hashOffset || uint64_t(special)*hashSize>hashOffset)
        return failure(EINVAL,"CodeDirectory coverage bounds",reason);
    // Verify the detached CMS and Apple Software Signing policy before trusting
    // any coverage result or installing an entry in the registration table.
    if (!adHoc && !verifyCMS(cmsEntry->second.bytes+8,cmsEntry->second.size-8,cd.bytes,cd.size,platformOnly))
        return failure(EPERM,platformOnly?"Apple Software Signing CMS validation failed":"Apple-rooted code-signing CMS validation failed",reason);
    std::vector<unsigned char> page(pageSize);std::array<unsigned char,EVP_MAX_MD_SIZE> hash{};unsigned digestSize=0;
    for (uint32_t i=0;i<slots;++i) {
        uint64_t offset=uint64_t(i)*pageSize;size_t size=std::min(pageSize,limit-offset);
        if (!readAt(fd,page.data(),size,slice+offset,before.st_size) ||
            EVP_Digest(page.data(),size,hash.data(),&digestSize,digest,nullptr)!=1 ||
            CRYPTO_memcmp(hash.data(),cd.bytes+hashOffset+uint64_t(i)*hashSize,hashSize)) return failure(EPERM,"signed code page mismatch",reason);
    }
    for (uint32_t slot:{2U,5U,7U}) if (slot<=special) {
        const unsigned char* expected=cd.bytes+hashOffset-uint64_t(slot)*hashSize;bool nonzero=false;
        for(unsigned i=0;i<hashSize;++i)nonzero|=expected[i]!=0;
        auto blob=blobs.find(slot);
        if (blob==blobs.end()) { if(nonzero)return failure(EPERM,"missing signed special slot",reason);continue; }
        if (EVP_Digest(blob->second.bytes,blob->second.size,hash.data(),&digestSize,digest,nullptr)!=1 || CRYPTO_memcmp(hash.data(),expected,hashSize))
            return failure(EPERM,"signed special slot mismatch",reason);
    }
    struct stat after{};if (fstat(fd,&after) || !sameFile(before,after)) return failure(EAGAIN,"file changed during verification",reason);
    auto registration=std::make_unique<Registered>();registration->fd=fcntl(fd,F_DUPFD_CLOEXEC,0);
    if(registration->fd<0)return failure(errno,"registration descriptor duplication failed",reason);
    registration->identity=after;registration->slice=slice;registration->covered=limit;registration->directory.assign(cd.bytes,cd.bytes+cd.size);
    {std::lock_guard<std::mutex> guard(registrationLock);
        registrations.erase(std::remove_if(registrations.begin(),registrations.end(),[&](const auto& prior){return prior->identity.st_dev==after.st_dev && prior->identity.st_ino==after.st_ino && prior->slice==slice;}),registrations.end());
        if(registrations.size()>=256)registrations.erase(registrations.begin());registrations.push_back(std::move(registration));
    }
    covered=limit;if(reason)*reason=adHoc?"verified and registered ad-hoc code coverage":"verified and registered Apple-signed code coverage";return 0;
}
}
int registerSimulatorDyld(int fd,uint64_t slice,uint64_t start,uint64_t size,uint64_t& covered,std::string* reason) {
    try { return verify(fd,slice,start,size,covered,reason,true); }
    catch(const std::bad_alloc&) {covered=0;return failure(ENOMEM,"allocation failed",reason);}
    catch(...) {covered=0;return failure(EIO,"signature verification failed",reason);}
}
int registerEmbeddedFile(int fd,uint64_t slice,uint64_t start,uint64_t size,uint64_t& covered,std::string* reason) {
    try { return verify(fd,slice,start,size,covered,reason,false); }
    catch(const std::bad_alloc&) {covered=0;return failure(ENOMEM,"allocation failed",reason);}
    catch(...) {covered=0;return failure(EIO,"signature verification failed",reason);}
}
}
