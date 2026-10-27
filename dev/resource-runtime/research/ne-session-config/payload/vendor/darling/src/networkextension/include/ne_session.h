#include <stdbool.h>
#include <uuid/uuid.h>

// The enum name is a guess
typedef enum ne_session_type {
    NESessionTypeAppVPN,
    NESessionTypeVPN
} ne_session_type_t;

bool ne_session_set_socket_attributes(int socket, char *hostname, void *unknown);
bool ne_session_app_vpn_configs_present(void);
bool ne_session_always_on_vpn_configs_present(void);
bool ne_session_on_demand_configs_present(void);
int ne_session_service_get_dns_service_id(uuid_t uuid, ne_session_type_t session_type, const char *hostname);

// not sure what this type is (it's probably an enum or enum-like type)
typedef int ne_session_status_t;
