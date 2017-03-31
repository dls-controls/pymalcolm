from malcolm.core import Post, Subscribe, Put, Controller, method_takes, \
    REQUIRED, Alarm, Process, Unsubscribe, Delta, deserialize_object, Queue
from malcolm.vmetas.builtin import StringMeta


@method_takes(
    "comms", StringMeta("Malcolm resource id of client comms"), REQUIRED,
    "mri", StringMeta("Malcolm resource id of created block"), REQUIRED)
class ProxyController(Controller):
    """Sync a local block with a given remote block"""
    def __init__(self, process, parts, params):
        self.params = params
        super(ProxyController, self).__init__(process, params.mri, parts)
        self.client_comms = process.get_controller(params.comms)
        self.set_health(self, Alarm.invalid("Uninitialized"))
        self._response_queue = Queue()

    @Process.Init
    def init(self):
        subscribe = Subscribe(
            path=[self.params.mri], delta=True, callback=self.handle_response)
        self.client_comms.send_to_server(subscribe)
        # TODO: should we wait until connected here?

    @Process.Halt
    def halt(self):
        unsubscribe = Unsubscribe(callback=self.handle_response)
        self.client_comms.send_to_server(unsubscribe)

    def handle_request(self, request):
        # Forward Puts and Posts to the client_comms
        if isinstance(request, (Put, Post)):
            return self.client_comms.send_to_server(request)
        else:
            return super(ProxyController, self).handle_request(request)

    def handle_response(self, response):
        self._response_queue.put(response)
        return self.spawn(self._handle_response)

    def _handle_response(self):
        with self.changes_squashed:
            response = self._response_queue.get(timeout=0)
            self.log_debug("Got response %s", response)
            response = deserialize_object(response, Delta)
            for change in response.changes:
                path = change[0]
                if len(path) == 0:
                    assert len(change) == 2, \
                        "Can't delete root block with change %r" % (change,)
                    self._regenerate_block(change[1])
                elif len(path) == 1 and path[0] not in ("health", "meta"):
                    if len(change) == 1:
                        # Delete a field
                        self._block.remove_endpoint(path[1])
                    else:
                        # Change a single field of the block
                        self._block.set_endpoint_data(path[1], change[1])
                elif len(path) == 2 and path[:1] == ["health", "alarm"]:
                    # If we got an alarm update for health
                    assert len(change) == 2, "Can't delete health alarm"
                    self.set_health(self, change[1])
                elif path[0] not in ("health", "meta"):
                    # Update a child of the block
                    assert len(change) == 2, \
                        "Can't delete entries in Attributes or Methods"
                    ob = self._block
                    for p in path[:-1]:
                        ob = ob[p]
                    getattr(ob, "set_%s" % path[-1])(change[1])
                else:
                    raise ValueError("Bad response %s" % response)

    def _regenerate_block(self, d):
        for field in list(self._block):
            if field not in ("health", "meta"):
                self._block.remove_endpoint(field)
        for field, value in d.items():
            if field == "health":
                if value["alarm"]["severity"]:
                    self.set_health(self, value["alarm"])
                else:
                    self.set_health(self, None)
            elif field == "meta":
                # TODO: set meta
                pass
            elif field != "typeid":
                # No need to set writeable_functions as the server will do it
                self._block.set_endpoint_data(field, value)
