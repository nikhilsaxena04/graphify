import json
import subprocess
from pathlib import Path

def test_php_inter_class_member_calls(tmp_path: Path):
    (tmp_path / "graphify.json").write_text(json.dumps({"languages": ["php"]}))
    
    (tmp_path / "mailer.php").write_text("""<?php
class EmailSender {
    public function prepareAndSendEmail() {
        empty($this);
    }
}
""")
    
    (tmp_path / "order.php").write_text("""<?php
class OrderService {
    public function __construct(
        private EmailSender $emailSender,
        private ExternalInterface $external
    ) {}
    
    private Logger $logger;

    public function send() {
        $this->emailSender->prepareAndSendEmail();
        $this->logger->log();
        $this->external->doThing();
        empty($this->emailSender);
    }
}
""")

    import sys
    subprocess.run([sys.executable, "-m", "graphify", "update", "."], cwd=str(tmp_path), check=True, env={"PYTHONPATH": str(Path.cwd())})
    
    graph_path = tmp_path / "graphify-out" / "graph.json"
    assert graph_path.exists()
    
    data = json.loads(graph_path.read_text())
    edges = data.get("links", [])
    nodes = {n["id"]: n for n in data.get("nodes", [])}
    
    def get_node_by_label(lbl):
        for nid, n in nodes.items():
            if lbl in n.get("label", ""):
                return nid
        return None

    send_nid = get_node_by_label(".send()")
    prepare_nid = get_node_by_label(".prepareAndSendEmail()")
    
    assert send_nid, ".send() not found"
    assert prepare_nid, ".prepareAndSendEmail() not found"
    
    # Check that OrderService.send() calls EmailSender.prepareAndSendEmail()
    calls_edge = False
    for e in edges:
        if e.get("source") == send_nid and e.get("target") == prepare_nid and e["relation"] == "calls":
            calls_edge = True
            assert e["confidence"] == "INFERRED"
    
    assert calls_edge, "Missing typed call edge for $this->emailSender->prepareAndSendEmail()"
    
    # Check that the unresolved calls are recorded
    send_node = nodes[send_nid]
    metadata = send_node.get("metadata", {})
    unresolved = metadata.get("unresolved_calls", [])
    
    found_logger = False
    found_external = False
    for u in unresolved:
        if u.get("callee") == "log" and u.get("receiver_type") == "Logger" and u.get("reason") == "external_unresolved":
            found_logger = True
        if u.get("callee") == "doThing" and u.get("receiver_type") == "ExternalInterface" and u.get("reason") == "external_unresolved":
            found_external = True
            
    assert found_logger, "Missing unresolved record for Logger.log()"
    assert found_external, "Missing unresolved record for ExternalInterface.doThing()"
    
    # Check that `empty` didn't generate a false edge
    for e in edges:
        if e["source"] == send_nid and e["relation"] == "calls":
            assert e["target"] != get_node_by_label("empty"), "empty() builtin falsely resolved"
