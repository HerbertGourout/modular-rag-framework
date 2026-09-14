# Integration-test policy for tests/integration/test_opa_egress_policy.py.
# Not a production policy: it exists to prove the adapter reads a real OPA
# decision, including an explicit deny and an undefined document.
package modular_rag.egress

default decision := {"allowed": false}

decision := {"allowed": true} if {
	input.provider == "openai"
	input.classification in {"public", "internal"}
}
