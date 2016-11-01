from collections import namedtuple

from malcolm.compat import OrderedDict
from malcolm.core.block import Block
from malcolm.core.cache import Cache
from malcolm.core.clientcontroller import ClientController
from malcolm.core.loggable import Loggable
from malcolm.core.request import Post, Put, Subscribe, Unsubscribe, Get
from malcolm.core.vmetas import StringArrayMeta

# Sentinel object that when received stops the recv_loop
PROCESS_STOP = object()

# Internal update messages
BlockChanges = namedtuple("BlockChanges", "changes")
BlockRespond = namedtuple("BlockRespond", "response, response_queue")
BlockAdd = namedtuple("BlockAdd", "block, name, controller")
BlockList = namedtuple("BlockList", "client_comms, blocks")
AddSpawned = namedtuple("AddSpawned", "spawned")


class Process(Loggable):
    """Hosts a number of Blocks, distributing requests between them"""

    def __init__(self, name, sync_factory):
        self.set_logger_name(name)
        self.name = name
        self.sync_factory = sync_factory
        self.q = self.create_queue()
        self._blocks = OrderedDict()  # block_name -> Block
        self._controllers = OrderedDict()  # block_name -> Controller
        self._block_state_cache = Cache()
        self._recv_spawned = None
        self._other_spawned = []
        # lookup of all Subscribe requests, ordered to guarantee subscription
        # notification ordering
        # {Request.generate_key(): Subscribe}
        self._subscriptions = OrderedDict()
        self.comms = []
        self._client_comms = OrderedDict()  # client comms -> list of blocks
        self._handle_functions = {
            Post: self._forward_block_request,
            Put: self._forward_block_request,
            Get: self._handle_get,
            Subscribe: self._handle_subscribe,
            Unsubscribe: self._handle_unsubscribe,
            BlockChanges: self._handle_block_changes,
            BlockRespond: self._handle_block_respond,
            BlockAdd: self._handle_block_add,
            BlockList: self._handle_block_list,
            AddSpawned: self._add_spawned,
        }
        self.create_process_block()

    def recv_loop(self):
        """Service self.q, distributing the requests to the right block"""
        while True:
            request = self.q.get()
            self.log_debug("Received request %s", request)
            if request is PROCESS_STOP:
                # Got the sentinel, stop immediately
                break
            try:
                self._handle_functions[type(request)](request)
            except Exception as e:  # pylint:disable=broad-except
                self.log_exception("Exception while handling %s", request)
                try:
                    request.respond_with_error(str(e))
                except Exception:
                    pass

    def add_comms(self, comms):
        assert not self._recv_spawned, \
            "Can't add comms when process has been started"
        self.comms.append(comms)

    def start(self):
        """Start the process going"""
        self._recv_spawned = self.sync_factory.spawn(self.recv_loop)
        for comms in self.comms:
            comms.start()

    def stop(self, timeout=None):
        """Stop the process and wait for it to finish

        Args:
            timeout (float): Maximum amount of time to wait for each spawned
            process. None means forever
        """
        assert self._recv_spawned, "Process not started"
        self.q.put(PROCESS_STOP)
        for comms in self.comms:
            comms.stop()
        # Wait for recv_loop to complete first
        self._recv_spawned.wait(timeout=timeout)
        # Now wait for anything it spawned to complete
        for s in self._other_spawned:
            s.wait(timeout=timeout)

    def _forward_block_request(self, request):
        """Lookup target Block and spawn block.handle_request(request)

        Args:
            request (Request): The message that should be passed to the Block
        """
        block_name = request.endpoint[0]
        block = self._blocks[block_name]
        self._other_spawned.append(
            self.sync_factory.spawn(block.handle_request, request))

    def create_queue(self):
        """
        Create a queue using sync_factory object

        Returns:
            Queue: New queue
        """

        return self.sync_factory.create_queue()

    def create_lock(self):
        """
        Create a lock using sync_factory object

        Returns:
            Lock: New lock
        """
        return self.sync_factory.create_lock()

    def spawn(self, function, *args, **kwargs):
        """Calls SyncFactory.spawn()"""
        def catching_function():
            try:
                function(*args, **kwargs)
            except Exception:
                self.log_exception(
                    "Exception calling %s(*%s, **%s)", function, args, kwargs)
                raise
        spawned = self.sync_factory.spawn(catching_function)
        request = AddSpawned(spawned)
        self.q.put(request)
        return spawned

    def _add_spawned(self, request):
        spawned = self._other_spawned
        self._other_spawned = []
        spawned.append(request.spawned)
        # Filter out the spawned that have completed to stop memory leaks
        for sp in spawned:
            if not sp.ready():
                self._other_spawned.append(sp)

    def get_client_comms(self, block_name):
        for client_comms, blocks in list(self._client_comms.items()):
            if block_name in blocks:
                return client_comms

    def create_process_block(self):
        self.process_block = Block()
        # TODO: add a meta here
        children = OrderedDict()
        children["blocks"] = StringArrayMeta(
            description="Blocks hosted by this Process"
        ).make_attribute([])
        children["remoteBlocks"] = StringArrayMeta(
                description="Blocks reachable via ClientComms"
        ).make_attribute([])
        self.process_block.replace_endpoints(children)
        self.process_block.set_parent(self, self.name)
        self.add_block(self.process_block, self)

    def update_block_list(self, client_comms, blocks):
        self.q.put(BlockList(client_comms=client_comms, blocks=blocks))

    def _handle_block_list(self, request):
        self._client_comms[request.client_comms] = request.blocks
        remotes = []
        for blocks in self._client_comms.values():
            remotes += [b for b in blocks if b not in remotes]
        self.process_block["remoteBlocks"].set_value(remotes)

    def _handle_block_changes(self, request):
        """Update subscribers with changes and applies stored changes to the
        cached structure"""
        # update cached dict
        self._block_state_cache.apply_changes(*request.changes)

        for subscription in self._subscriptions.values():
            endpoint = subscription.endpoint
            # find stuff that's changed that is relevant to this subscriber
            changes = []
            for change in request.changes:
                change_path = change[0]
                # look for a change_path where the beginning matches the
                # endpoint path, then strip away the matching part and add
                # to the change set
                i = 0
                for (cp_element, ep_element) in zip(change_path, endpoint):
                    if cp_element != ep_element:
                        break
                    i += 1
                else:
                    # change has matching path, so keep it
                    # but strip off the end point path
                    filtered_change = [change_path[i:]] + change[1:]
                    changes.append(filtered_change)
            if len(changes) > 0:
                if subscription.delta:
                    # respond with the filtered changes
                    subscription.respond_with_delta(changes)
                else:
                    # respond with the structure of everything
                    # below the endpoint
                    d = self._block_state_cache.walk_path(endpoint)
                    subscription.respond_with_update(d)

    def report_changes(self, *changes):
        self.q.put(BlockChanges(changes=list(changes)))

    def block_respond(self, response, response_queue):
        self.q.put(BlockRespond(response, response_queue))

    def _handle_block_respond(self, request):
        """Push the response to the required queue"""
        request.response_queue.put(request.response)

    def add_block(self, block, controller):
        """Add a block to be hosted by this process

        Args:
            block (Block): The block to be added
            controller (Controller): Its controller
        """
        path = block.path_relative_to(self)
        assert len(path) == 1, \
            "Expected block %r to have %r as parent, got path %r" % \
            (block, self, path)
        name = path[0]
        assert name not in self._blocks, \
            "There is already a block called %r" % name
        request = BlockAdd(block=block, controller=controller, name=name)
        if self._recv_spawned:
            # Started, so call in Process thread
            self.q.put(request)
        else:
            # Not started yet so we are safe to add in this thread
            self._handle_block_add(request)

    def _handle_block_add(self, request):
        """Add a block to be hosted by this process"""
        assert request.name not in self._blocks, \
            "There is already a block called %r" % request.name
        self._blocks[request.name] = request.block
        self._controllers[request.name] = request.controller
        serialized = request.block.to_dict()
        change_request = BlockChanges([[[request.name], serialized]])
        self._handle_block_changes(change_request)
        # Regenerate list of blocks
        self.process_block["blocks"].set_value(list(self._blocks))

    def get_block(self, block_name):
        try:
            return self._blocks[block_name]
        except KeyError:
            params = ClientController.MethodMeta.prepare_input_map(
                mri=block_name)
            controller = ClientController(self, {}, params)
            return controller.block

    def get_controller(self, block_name):
        return self._controllers[block_name]

    def _handle_subscribe(self, request):
        """Add a new subscriber and respond with the current
        sub-structure state"""
        key = request.generate_key()
        assert key not in self._subscriptions, \
            "Subscription on %s already exists" % (key,)
        self._subscriptions[key] = request
        d = self._block_state_cache.walk_path(request.endpoint)
        self.log_debug("Initial subscription value %s", d)
        if request.delta:
            request.respond_with_delta([[[], d]])
        else:
            request.respond_with_update(d)

    def _handle_unsubscribe(self, request):
        """Remove a subscriber and respond with success or error"""
        key = request.generate_key()
        try:
            subscription = self._subscriptions.pop(key)
        except KeyError:
            request.respond_with_error(
                "No subscription found for %s" % (key,))
        else:
            request.respond_with_return()

    def _handle_get(self, request):
        d = self._block_state_cache.walk_path(request.endpoint)
        request.respond_with_return(d)
