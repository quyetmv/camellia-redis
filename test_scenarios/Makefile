# Makefile điều phối chung cho các kịch bản kiểm thử Camellia

NAMESPACE = testing

# Lấy địa chỉ IP của Node K8s đầu tiên (Internal IP)
NODE_IP := $(shell kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || echo localhost)
CLIENT_MODE= standalone
# Detect NodePorts
KEY_ROUTING_PORT := $(shell kubectl get svc svc-camellia-proxy-cluster-key-routing -n $(NAMESPACE) -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 30681)
SHARED_AUTH_PORT := $(shell kubectl get svc svc-camellia-proxy-cluster-shared-auth -n $(NAMESPACE) -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 30680)
DASHBOARD_PORT    := $(shell kubectl get svc svc-camellia-dashboard -n $(NAMESPACE) -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 30881)
KEY_ROUTING_PORT_STANDALONE := $(shell kubectl get svc svc-camellia-proxy-standalone-key-routing -n $(NAMESPACE) -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 31681)
SHARED_AUTH_PORT_STANDALONE := $(shell kubectl get svc svc-camellia-proxy-standalone-shared-auth -n $(NAMESPACE) -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo 31680)

.PHONY: all info test-proxy test-proxy-standalone test-dashboard clean

all: test-proxy

info:
	@echo "========================================================"
	@echo "    Camellia Global Test Suite - Dynamic Endpoints"
	@echo "========================================================"
	@echo "Namespace       : $(NAMESPACE)"
	@echo "Proxy Host (Node): $(NODE_IP)"
	@echo "Client Mode     : $(if $(CLIENT_MODE),$(CLIENT_MODE),standalone)"
	@echo "--------------------------------------------------------"
	@echo "Detected Ports:"
	@echo "  [Key Routing]   : $(KEY_ROUTING_PORT)"
	@echo "  [Shared Auth]   : $(SHARED_AUTH_PORT)"
	@echo "  [Dashboard]     : $(DASHBOARD_PORT)"
	@echo "========================================================"

# Test Suite 1: Chỉ nhắm vào Proxy (Sử dụng config tĩnh)
test-proxy: info
	@echo ">> Chạy PROXY-ONLY Test Suite (No Dashboard)..."
	cd 1-proxy-only && \
	PROXY_HOST=$(NODE_IP) \
	CLIENT_MODE=$(if $(CLIENT_MODE),$(CLIENT_MODE),standalone) \
	KEY_ROUTING_PORT=$(KEY_ROUTING_PORT) \
	SHARED_AUTH_PORT=$(SHARED_AUTH_PORT) \
	python3 test_proxy_core.py

# Test Suite standalone-only (không dùng cluster client)
test-proxy-standalone: info
	@echo ">> Chạy PROXY-ONLY Standalone Test Suite..."
	cd 1-proxy-only && \
	PROXY_HOST=$(NODE_IP) \
	KEY_ROUTING_PORT=$(KEY_ROUTING_PORT_STANDALONE) \
	SHARED_AUTH_PORT=$(SHARED_AUTH_PORT_STANDALONE) \
	python3 test_proxy_standalone.py

# Test Suite 2: Test tích hợp với Dashboard
test-dashboard: info
	@echo ">> Chạy DASHBOARD-INTEGRATION Test Suite..."
	cd 2-with-dashboard && \
	PROXY_HOST=$(NODE_IP) \
	CLIENT_MODE=$(if $(CLIENT_MODE),$(CLIENT_MODE),standalone) \
	KEY_ROUTING_PORT=$(KEY_ROUTING_PORT) \
	SHARED_AUTH_PORT=$(SHARED_AUTH_PORT) \
	DASHBOARD_URL=http://$(NODE_IP):$(DASHBOARD_PORT) \
	python3 test_dashboard_integration.py

# Alias cho lệnh cũ
test: test-proxy
