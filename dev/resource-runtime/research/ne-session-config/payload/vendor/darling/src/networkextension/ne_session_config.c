#include <ne_session.h>
#include <notify.h>
#include <pthread.h>
#include <stdint.h>

static pthread_mutex_t config_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t config_once = PTHREAD_ONCE_INIT;
static int config_token = -1;
static uint64_t config_state;

static void before_fork(void) { pthread_mutex_lock(&config_mutex); }
static void after_fork_parent(void) { pthread_mutex_unlock(&config_mutex); }
static void after_fork_child(void)
{
    /* Notify tokens belong to the registering process. Do not cancel the
     * parent's token from the child or carry a stale cached state forward. */
    config_token = -1;
    config_state = 0;
    pthread_mutex_unlock(&config_mutex);
}
static void setup_config_cache(void)
{
    pthread_atfork(before_fork, after_fork_parent, after_fork_child);
}

static uint64_t current_config_state(void)
{
    /* This module is also a libSystem component. Register lazily after the
     * umbrella has initialized; a dylib constructor would create a cycle. */
    pthread_once(&config_once, setup_config_cache);
    pthread_mutex_lock(&config_mutex);
    if (config_token < 0) {
        if (notify_register_check("com.apple.neconfigurationchanged", &config_token) != NOTIFY_STATUS_OK)
            config_token = -1;
    }
    if (config_token >= 0) {
        int changed = 0;
        uint32_t status = notify_check(config_token, &changed);
        if (status == NOTIFY_STATUS_OK && changed)
            status = notify_get_state(config_token, &config_state);
        if (status != NOTIFY_STATUS_OK) {
            notify_cancel(config_token);
            config_token = -1;
            config_state = 0;
        }
    }
    uint64_t state = config_state;
    pthread_mutex_unlock(&config_mutex);
    return state;
}

bool ne_session_app_vpn_configs_present(void) { return ((current_config_state() >> 62) & 1) != 0; }
bool ne_session_always_on_vpn_configs_present(void) { return ((current_config_state() >> 61) & 1) != 0; }
bool ne_session_on_demand_configs_present(void) { return (current_config_state() >> 63) != 0; }
