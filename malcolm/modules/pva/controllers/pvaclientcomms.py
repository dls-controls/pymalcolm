from p4p import Value
from p4p.client.raw import Disconnected
from p4p.nt import NTURI
from annotypes import TYPE_CHECKING

from malcolm.compat import maybe_import_cothread
from malcolm.modules.builtin.controllers import ClientComms
from malcolm.core import Queue, Model, DEFAULT_TIMEOUT, BlockMeta, \
    serialize_object, BlockModel, Alarm
from .pvaconvert import convert_value_to_dict, convert_to_type_tuple_value, Type


if TYPE_CHECKING:
    from typing import Set


class PvaClientComms(ClientComms):
    """A class for a client to communicate with the server"""

    _monitors = None
    _ctxt = None

    def do_init(self):
        super(PvaClientComms, self).do_init()
        cothread = maybe_import_cothread()
        if cothread:
            from p4p.client.cothread import Context, Subscription
        else:
            from p4p.client.thread import Context, Subscription
        self._ctxt = Context("pva", unwrap=False)
        self._monitors = set()  # type: Set[Subscription]

    def do_disable(self):
        super(PvaClientComms, self).do_disable()
        # Unsubscribe to all the monitors
        for m in self._monitors:
            m.close()
        self._ctxt.close()

    def _update_settable_fields(self, update_fields, dotted_path, ob):
        # type: (Set[str], str, Any) -> None
        if isinstance(ob, (Model, dict)):
            # Recurse down
            for k in ob:
                self._update_settable_fields(
                    update_fields, "%s.%s" % (dotted_path, k), ob[k])
        else:
            # This is a terminal field, add to the set
            update_fields.add(dotted_path)

    def sync_proxy(self, mri, block):
        """Abstract method telling the ClientComms to sync this proxy Block
        with its remote counterpart. Should wait until it is connected

        Args:
            mri (str): The mri for the remote block
            block (BlockModel): The local proxy Block to keep in sync
        """
        done_queue = Queue()
        update_fields = set()

        def callback(value=None):
            if isinstance(value, Exception):
                # Disconnect or Cancelled or RemoteError
                if isinstance(value, Disconnected):
                    # We will get a reconnect with a whole new structure
                    update_fields.clear()
                    block.health.set_value(
                        value="pvAccess disconnected",
                        alarm=Alarm.disconnected("pvAccess disconnected")
                    )
            else:
                with block.notifier.changes_squashed:
                    if not update_fields:
                        self._regenerate_block(block, value, update_fields)
                        done_queue.put(None)
                    else:
                        self._update_block(block, value, update_fields)

        m = self._ctxt.monitor(mri, callback, notify_disconnect=True)
        self._monitors.add(m)
        done_queue.get(timeout=DEFAULT_TIMEOUT)

    def _regenerate_block(self, block, value, update_fields):
        # type: (BlockModel, Value, Set[str]) -> None
        # This is an initial update, generate the list of all fields
        for k, v in value.items():
            if k == "health":
                # Update health attribute
                block.health.set_value(
                    value=v["value"],
                    alarm=convert_value_to_dict(v["alarm"]),
                    ts=convert_value_to_dict(v["timeStamp"]))
            elif k == "meta":
                # Update BlockMeta
                meta = block.meta  # type: BlockMeta
                for n in meta.call_types:
                    meta.apply_change([n], v[n])
            else:
                # Add new Attribute/Method
                v = convert_value_to_dict(v)
                block.set_endpoint_data(k, v)
            # Update the list of fields
            self._update_settable_fields(update_fields, k, block[k])

    def _update_block(self, block, value, update_fields):
        # type: (BlockModel, Value, Set[str]) -> None
        # This is a subsequent update
        changed = value.changedSet(parents=True, expand=False)
        for k in changed.intersection(update_fields):
            v = value[k]
            if isinstance(v, Value):
                v = convert_value_to_dict(v)
            self.log.debug("Applying %s %s", k, v)
            block.apply_change(k.split("."), v)

    def send_put(self, mri, attribute_name, value):
        """Abstract method to dispatch a Put to the server

        Args:
            mri (str): The mri of the Block
            attribute_name (str): The name of the Attribute within the Block
            value: The value to put
        """
        path = attribute_name + ".value"
        typ, value = convert_to_type_tuple_value(serialize_object(value))
        if isinstance(typ, tuple):
            # Structure, make into a Value
            _, typeid, fields = typ
            value = Value(Type(fields, typeid), value)
        self._ctxt.put(mri, {path: value}, path)

    def send_post(self, mri, method_name, **params):
        """Abstract method to dispatch a Post to the server

        Args:
            mri (str): The mri of the Block
            method_name (str): The name of the Method within the Block
            params: The parameters to send

        Returns:
            The return results from the server
        """
        typ, parameters = convert_to_type_tuple_value(serialize_object(params))
        uri = NTURI(typ[2])

        uri = uri.wrap(
            path="%s.%s" % (mri, method_name),
            kws=parameters,
            scheme="pva"
        )
        value = self._ctxt.rpc(mri, uri, timeout=None)
        return convert_value_to_dict(value)



