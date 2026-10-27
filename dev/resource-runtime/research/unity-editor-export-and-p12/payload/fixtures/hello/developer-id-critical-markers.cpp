#include "../../vendor/darlingserver/src/file-signatures.cpp"
#include <cstdio>
struct Marker {const char* oid;bool nullValue;};
int main(){
    EVP_PKEY_CTX* generation=EVP_PKEY_CTX_new_id(EVP_PKEY_RSA,nullptr);EVP_PKEY* key=nullptr;
    if(!generation||EVP_PKEY_keygen_init(generation)<=0||EVP_PKEY_CTX_set_rsa_keygen_bits(generation,2048)<=0||EVP_PKEY_keygen(generation,&key)<=0)return 2;
    EVP_PKEY_CTX_free(generation);unsigned checks=0;
    auto check=[&](const char* name,std::initializer_list<Marker> markers,bool expected,int depth=0,bool eku=true){
        X509* cert=X509_new();X509_set_version(cert,2);X509_set_pubkey(cert,key);
        if(eku){X509_EXTENSION* ext=X509V3_EXT_conf_nid(nullptr,nullptr,NID_ext_key_usage,const_cast<char*>("critical,codeSigning"));X509_add_ext(cert,ext,-1);X509_EXTENSION_free(ext);}
        for(auto marker:markers){
            ASN1_OBJECT* oid=OBJ_txt2obj(marker.oid,1);ASN1_OCTET_STRING* value=ASN1_OCTET_STRING_new();
            const unsigned char valid[]={5,0},invalid[]={4,0};ASN1_OCTET_STRING_set(value,marker.nullValue?valid:invalid,2);
            X509_EXTENSION* ext=X509_EXTENSION_create_by_OBJ(nullptr,oid,1,value);X509_add_ext(cert,ext,-1);
            X509_EXTENSION_free(ext);ASN1_OCTET_STRING_free(value);ASN1_OBJECT_free(oid);
        }
        X509_STORE_CTX* ctx=X509_STORE_CTX_new();X509_STORE_CTX_set_current_cert(ctx,cert);X509_STORE_CTX_set_error_depth(ctx,depth);X509_STORE_CTX_set_error(ctx,X509_V_ERR_UNHANDLED_CRITICAL_EXTENSION);
        bool actual=DarlingServer::FileSignatures::verifyKnownAppleCriticalExtension(0,ctx);
        X509_STORE_CTX_free(ctx);X509_free(cert);printf("%s %s\n",name,actual==expected?"PASS":"FAIL");checks++;return actual==expected;
    };
    constexpr const char* application="1.2.840.113635.100.6.1.13";constexpr const char* kernel="1.2.840.113635.100.6.1.18";
    bool ok=check("Application",{{application,true}},true);
    ok&=check("Application-with-optional-kernel-marker",{{application,true},{kernel,true}},true);
    ok&=check("Kernel-marker-without-Application",{{kernel,true}},false);
    ok&=check("Unknown-critical-extension",{{application,true},{"1.2.3.4.5",true}},false);
    ok&=check("Duplicate-Application",{{application,true},{application,true}},false);
    ok&=check("Invalid-Application-DER",{{application,false},{kernel,true}},false);
    ok&=check("Invalid-kernel-DER",{{application,true},{kernel,false}},false);
    ok&=check("Intermediate-marker",{{application,true},{kernel,true}},false,1);
    ok&=check("Missing-code-signing-EKU",{{application,true},{kernel,true}},false,0,false);
    EVP_PKEY_free(key);printf("MARKER_CHECKS %u\n",checks);return ok?0:1;
}
