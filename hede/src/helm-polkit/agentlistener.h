#pragma once

extern "C" {
#include <polkitagent/polkitagent.h>
}

class AgentController;

// Create HeDE's PolkitAgentListener subclass bound to the controller. Returned as
// the base PolkitAgentListener* for polkit_agent_listener_register().
PolkitAgentListener *helm_agent_listener_new(AgentController *controller);
