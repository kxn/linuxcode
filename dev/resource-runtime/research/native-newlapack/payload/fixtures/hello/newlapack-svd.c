#define ACCELERATE_NEW_LAPACK
#include <Accelerate/Accelerate.h>
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(__LAPACK_int) == 4, "NEWLAPACK LP64 integer ABI");
static unsigned checks, matrices;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL %d %s\n",__LINE__,#x); exit(2); } } while(0)
static const double guard = -987654321.125;
struct info_guard { uint32_t before; __LAPACK_int value; uint32_t after; };

static void svd(int mvalue, int nvalue, unsigned kind, double scale) {
    __LAPACK_int m=mvalue,n=nvalue,lda=m+2,ldu=m+1,ldvt=n+1,lwork=-1;
    unsigned k=m<n?m:n;
    char job='A';
    double a[64],input[64],saved[64],s[10],u[64],vt[64],query;
    for(unsigned i=0;i<64;++i) a[i]=input[i]=u[i]=vt[i]=guard;
    for(unsigned i=0;i<10;++i) s[i]=guard;
    for(int c=0;c<n;++c) for(int row=0;row<m;++row) {
        double x=0;
        if(kind==1) x=row==c ? (double)(m-row) : 0;
        if(kind==2) x=(row+1)*(c+1);
        if(kind==3) x=((row*13+c*7+3)%17-8)/6.0;
        a[c*lda+row]=input[c*lda+row]=x*scale;
    }
    memcpy(saved,a,sizeof(a));
    struct info_guard info={0xaabbccdd,-999,0x12345678};
    dgesvd_(&job,&job,&m,&n,a,&lda,s+1,u,&ldu,vt,&ldvt,&query,&lwork,&info.value);
    CHECK(info.value==0 && info.before==0xaabbccdd && info.after==0x12345678);
    CHECK(m==mvalue && n==nvalue && lda==m+2 && ldu==m+1 && ldvt==n+1);
    CHECK(!memcmp(a,saved,sizeof(a)));
    CHECK(isfinite(query) && query>=1 && query<10000000);
    lwork=(__LAPACK_int)ceil(query);
    double* allocation=malloc((lwork+2)*sizeof(double));CHECK(allocation);
    allocation[0]=allocation[lwork+1]=guard;
    info.value=-999;
    dgesvd_(&job,&job,&m,&n,a,&lda,s+1,u,&ldu,vt,&ldvt,allocation+1,&lwork,&info.value);
    CHECK(info.value==0 && info.before==0xaabbccdd && info.after==0x12345678);
    CHECK(allocation[0]==guard && allocation[lwork+1]==guard);
    free(allocation);
    CHECK(s[0]==guard && s[k+1]==guard);
    for(unsigned i=0;i<k;++i) {
        CHECK(isfinite(s[i+1]) && s[i+1]>=0);
        if(i) CHECK(s[i]>=s[i+1]);
    }
    for(int c=0;c<n;++c) for(int row=m;row<lda;++row) CHECK(a[c*lda+row]==guard);
    for(int c=0;c<m;++c) CHECK(u[c*ldu+m]==guard);
    for(int c=0;c<n;++c) CHECK(vt[c*ldvt+n]==guard);
    double error=0,norm=0;
    for(int c=0;c<n;++c) for(int row=0;row<m;++row) {
        double x=0;
        for(unsigned j=0;j<k;++j) x+=u[j*ldu+row]*s[j+1]*vt[c*ldvt+j];
        double expected=input[c*lda+row],delta=(x-expected)/scale;
        error+=delta*delta;norm+=(expected/scale)*(expected/scale);
    }
    double residual=norm?sqrt(error/norm):sqrt(error);
    CHECK(isfinite(residual) && residual<5e-13);
    for(int i=0;i<m;++i) for(int j=0;j<m;++j) {
        double dot=0;for(int row=0;row<m;++row) dot+=u[i*ldu+row]*u[j*ldu+row];
        CHECK(fabs(dot-(i==j))<5e-13);
    }
    for(int i=0;i<n;++i) for(int j=0;j<n;++j) {
        double dot=0;for(int col=0;col<n;++col) dot+=vt[col*ldvt+i]*vt[col*ldvt+j];
        CHECK(fabs(dot-(i==j))<5e-13);
    }
    if(kind==1) for(unsigned i=0;i<k;++i) CHECK(fabs(s[i+1]/scale-(m-i))<5e-13);
    if(kind==2) {
        double um=0,vn=0;
        for(int i=1;i<=m;++i) um+=i*i;
        for(int i=1;i<=n;++i) vn+=i*i;
        CHECK(fabs(s[1]/scale-sqrt(um*vn))<5e-12);
        for(unsigned i=1;i<k;++i) CHECK(s[i+1]/scale<5e-12);
    }
    ++matrices;
    printf("NEWLAPACK_SVD_CASE m=%d n=%d kind=%u scale=%.1e residual=%.17g\n",m,n,kind,scale,residual);
}

int main(int argc,char** argv) {
    CHECK(argc==2);
    svd(2,2,1,1);
    void* framework=dlopen("/System/Library/Frameworks/Accelerate.framework/Versions/A/Accelerate",RTLD_LAZY|RTLD_LOCAL);
    CHECK(framework);
    void* symbol=dlsym(framework,"dgesvd$NEWLAPACK");CHECK(symbol && symbol==(void*)dgesvd_);
    CHECK(!dlsym(framework,"deliberately_absent_newlapack_fixture_symbol"));
    Dl_info owner;CHECK(dladdr(symbol,&owner));CHECK(strstr(owner.dli_fname,argv[1]));
    printf("NEWLAPACK_DGESVD_OWNER %s\n",owner.dli_fname);
    for(unsigned kind=0;kind<4;++kind) {
        svd(4,3,kind,1);
        svd(3,4,kind,1);
    }
    svd(5,4,3,1e100);
    svd(5,4,3,1e-100);
    svd(1,1,1,1);
    CHECK(dlclose(framework)==0);
    printf("NEWLAPACK_LP64_SVD_WORKSPACE_GUARDS_SINGULAR_VALUES_ORTHOGONALITY_AND_RESIDUALS_OK checks=%u matrices=%u\n",checks,matrices);
}
