/* Linux/Darling glue for the original XNU Bank and ledger implementations. */
#include <darlingserver/duct-tape.h>
#include <darlingserver/duct-tape/task.h>
#include <darlingserver/duct-tape/hooks.internal.h>
#include <kern/task.h>
#include <kern/thread.h>
#include <kern/sched_prim.h>
#include <kern/ast.h>
#include <kern/policy_internal.h>
#include <kern/ledger.h>
#include <kern/zalloc.h>
#include <bank/bank_types.h>
#include <sys/persona.h>
#include <string.h>

struct _task_ledger_indices task_ledgers;
static ledger_template_t bank_task_template;
static zone_t private_pmap_ledger_zone;

void dtape_bank_ledger_init(void) {
    memset(&task_ledgers,0xff,sizeof task_ledgers);
    bank_task_template=ledger_template_create("Darling task Bank ledger");
    if (!bank_task_template) panic("Cannot allocate task Bank ledger template");
    task_ledgers.cpu_time_billed_to_me=ledger_entry_add(bank_task_template,"cpu_to_me","sched","ns");
    task_ledgers.cpu_time_billed_to_others=ledger_entry_add(bank_task_template,"cpu_to_others","sched","ns");
    task_ledgers.energy_billed_to_me=ledger_entry_add(bank_task_template,"energy_to_me","power","nj");
    task_ledgers.energy_billed_to_others=ledger_entry_add(bank_task_template,"energy_to_others","power","nj");
    if (task_ledgers.cpu_time_billed_to_me<0 || task_ledgers.cpu_time_billed_to_others<0 ||
            task_ledgers.energy_billed_to_me<0 || task_ledgers.energy_billed_to_others<0)
        panic("Cannot create task Bank ledger entries");
    ledger_template_complete(bank_task_template);
}

void dtape_bank_prepare_task(task_t task) {
    if (!bank_task_template) panic("Bank ledger used before initialization");
    task_lock(task);
    bool exists=task->ledger != LEDGER_NULL;
    task_unlock(task);
    if (exists) return;
    ledger_t candidate=ledger_instantiate(bank_task_template,LEDGER_CREATE_ACTIVE_ENTRIES);
    if (!candidate) panic("Cannot instantiate task Bank ledger");
    task_lock(task);
    if (!task->ledger) { task->ledger=candidate; candidate=LEDGER_NULL; }
    task_unlock(task);
    if (candidate) ledger_dereference(candidate);
}

void dtape_bank_destroy_task(task_t task) {
    if (task->bank_context) bank_task_destroy(task);
    if (task->ledger) { ledger_t ledger=task->ledger;task->ledger=LEDGER_NULL;ledger_dereference(ledger); }
}

void* get_bsdtask_info(task_t task) { return dtape_task_for_xnu_task(task); }
uint64_t proc_uniqueid(void* process) {
    dtape_task_t* task=process ? process : dtape_task_for_xnu_task(current_task());
    return task->p_ident.eid;
}
uint32_t proc_getuid(void* process) {
    dtape_task_t* task=process ? process : dtape_task_for_xnu_task(current_task());
    return task->xnu_task.audit_token.val[1];
}
uint32_t proc_getgid(void* process) {
    dtape_task_t* task=process ? process : dtape_task_for_xnu_task(current_task());
    return task->xnu_task.audit_token.val[2];
}

/* Darling has no alternate-persona service. Report absence and reject persona
 * changes rather than accepting new identities through the generic IOKit stub.
 */
int unique_persona=0;
struct persona *system_persona=NULL,*proxy_system_persona=NULL;
uint32_t proc_persona_id(void* unused) { return PERSONA_ID_NONE; }
uint32_t persona_get_id(struct persona* persona) { return PERSONA_ID_NONE; }
struct persona* persona_lookup(uint32_t id) { return NULL; }
void persona_put(struct persona* persona) { }

boolean_t task_is_app(task_t task) {
    switch (task->requested_policy.trp_apptype) {
    case TASK_APPTYPE_APP_DEFAULT: case TASK_APPTYPE_APP_TAL:return TRUE;
    default:return FALSE;
    }
}

void proc_getexecutableuuid(void* process,unsigned char* uuid,unsigned long size) {
    if (!uuid || size<16) return;
    memset(uuid,0,16);
    dtape_task_t* task=process ? process : dtape_task_for_xnu_task(current_task());
    struct { uint32_t version,count; uint64_t images; } info;
    uint64_t executable=0;
    uintptr_t info_address;
    dtape_mutex_lock(&task->dyld_info_lock);
    info_address=task->dyld_info_addr;
    dtape_mutex_unlock(&task->dyld_info_lock);
    if (!task->context || !info_address || !dtape_hooks->task_read_memory(task->context,info_address,&info,sizeof info) || !info.count || !info.images ||
            !dtape_hooks->task_read_memory(task->context,info.images,&executable,sizeof executable)) return;
    struct {uint32_t magic,cpu,subtype,type,commands,command_bytes,flags,reserved;} header;
    if (!dtape_hooks->task_read_memory(task->context,executable,&header,sizeof header) || header.magic!=0xfeedfacf || header.commands>2048 || header.command_bytes>(16u<<20)) return;
    uint64_t at=executable+sizeof header,end=at+header.command_bytes;
    if (at<executable || end<at) return;
    for (uint32_t i=0;i<header.commands;i++) {
        struct {uint32_t cmd,size;} load;
        if (at>end || end-at<sizeof load || !dtape_hooks->task_read_memory(task->context,at,&load,sizeof load) || load.size<8 || load.size>end-at) return;
        if (load.cmd==0x1b && load.size==24) {
            dtape_hooks->task_read_memory(task->context,at+8,uuid,16);return;
        }
        at+=load.size;
    }
}

/* The Linux server stores ordinary ledgers in private zones. This allocator
 * does not advertise hardware page-protection / PPL support.
 */
void pmap_ledger_alloc_init(size_t size) {
    if (private_pmap_ledger_zone) panic("Duplicate private ledger zone initialization");
    private_pmap_ledger_zone=zone_create("Darling private ledger",size,ZC_NONE);
}
ledger_t pmap_ledger_alloc(void) {
    return private_pmap_ledger_zone ? zalloc(private_pmap_ledger_zone) : LEDGER_NULL;
}
void pmap_ledger_free(ledger_t ledger) { zfree(private_pmap_ledger_zone,ledger); }
ledger_t coalition_ledger_get_from_task(task_t task) { return LEDGER_NULL; }

void act_set_astledger_async(thread_t thread) { __atomic_fetch_or(&thread->ast,AST_LEDGER,__ATOMIC_RELEASE); }
wait_result_t thread_block_reason(thread_continue_t continuation,void* parameter,ast_t reason) {
    return thread_block_parameter(continuation,parameter);
}
int thread_get_cpulimit(int* action,uint8_t* percentage,uint64_t* interval) {
    if (action) *action=THREAD_CPULIMIT_DISABLE;
    if (percentage) *percentage=0;
    if (interval) *interval=0;
    return KERN_SUCCESS;
}
int thread_set_cpulimit(int action,uint8_t percentage,uint64_t interval) {
    return action==THREAD_CPULIMIT_DISABLE ? KERN_SUCCESS : KERN_NOT_SUPPORTED;
}
/* No energy counter is installed for this Linux compatibility target. */
uint64_t ml_energy_stat(thread_t thread) { return 0; }
