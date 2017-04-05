import weakref
import time

from .future import Future
from .loggable import Loggable
from .request import Put, Post, Subscribe, Unsubscribe
from .response import Update, Return, Error
from .queue import Queue
from .errors import TimeoutError, AbortedError, UnexpectedError, \
    ResponseError, BadValueError


class When(object):
    def __init__(self, condition_satisfied):
        self.condition_satisfied = condition_satisfied
        self.future = None
        self.context = None

    def set_future_context(self, future, context):
        self.future = future
        self.context = context

    def check_condition(self, value):
        try:
            if self.condition_satisfied(value):
                # All done, so unsubscribe
                self.context.unsubscribe(self.future)
        except Exception:
            # Bad value, so unsubscribe
            self.context.unsubscribe(self.future)
            raise


class Context(Loggable):
    STOP = object()
    runner = None

    def __init__(self, name, process):
        self.set_logger_name(name)
        self._q = Queue()
        self._process = process
        self._next_id = 1
        self._futures = {}  # dict {int id: Future)}
        self._subscriptions = {}  # dict {int id: (func, args)}
        self._requests = {}  # dict {Future: Request}
        # If not None, wait for this before listening to STOPs
        self._sentinel_stop = None

    def get_controller(self, mri):
        controller = self._process.get_controller(mri)
        return controller

    def block_view(self, mri):
        controller = self.get_controller(mri)
        block = controller.make_view(weakref.proxy(self))
        return block

    def _get_next_id(self):
        new_id = self._next_id
        self._next_id += 1
        return new_id

    def _dispatch_request(self, request):
        future = Future(weakref.proxy(self))
        self._futures[request.id] = future
        self._requests[future] = request
        controller = self.get_controller(request.path[0])
        controller.handle_request(request)
        return future

    def ignore_stops_before_now(self):
        """Ignore any stops received before this point"""
        self._sentinel_stop = object()
        self._q.put(self._sentinel_stop)

    def stop(self):
        """Stops any wait_all_futures call with an AbortedError"""
        self._q.put(self.STOP)

    def put(self, path, value, timeout=None):
        """"Puts a value to a path and returns when it completes

        Args:
            path (list): The path to put to
            value (object): The value to set
            timeout (float): time in seconds to wait for responses, wait forever
                if None
        """
        future = self.put_async(path, value)
        self.wait_all_futures(future, timeout=timeout)

    def put_async(self, path, value):
        """"Puts a value to a path and returns immediately

        Args:
            path (list): The path to put to
            value (object): The value to set

        Returns:
             Future: A single Future which will resolve to the result
        """
        request = Put(self._get_next_id(), path, value, self._q.put)
        future = self._dispatch_request(request)
        return future

    def post(self, path, params=None, timeout=None):
        """Synchronously calls a method

        Args:
            path (list): The path to post to
            params (dict): parameters for the call
            timeout (float): time in seconds to wait for responses, wait
                forever if None

        Returns:
            the result from 'method'
        """
        future = self.post_async(path, params)
        self.wait_all_futures(future, timeout=timeout)
        return future.result()

    def post_async(self, path, params=None):
        """Asynchronously calls a function on a child block

        Args:
            path (list): The path to post to
            params (dict): parameters for the call

        Returns:
             Future: as single Future that will resolve to the result
        """
        request = Post(self._get_next_id(), path, params, self._q.put)
        future = self._dispatch_request(request)
        return future

    def subscribe(self, path, callback, *args):
        """Subscribe to changes in a given attribute and call
        ``callback(future, value, *args)`` when it changes

        Returns:
            Future: A single Future which will resolve to the result
        """
        request = Subscribe(self._get_next_id(), path, False, self._q.put)
        # If self is in args, then make weak version of it
        saved_args = []
        for arg in args:
            if arg is self:
                saved_args.append(weakref.proxy(self))
            else:
                saved_args.append(arg)
        future = self._dispatch_request(request)
        self._subscriptions[request.id] = (callback, saved_args)
        return future

    def unsubscribe(self, future):
        """Terminates the subscription given by a future

        Args:
            future (Future): The future of the original subscription
        """
        subscribe = self._requests[future]
        request = Unsubscribe(subscribe.id, self._q.put)
        controller = self.get_controller(subscribe.path[0])
        controller.handle_request(request)

    def unsubscribe_all(self):
        """Send an unsubscribe for all active subscriptions"""
        futures = [f for f, r in self._requests.items()
                   if isinstance(r, Subscribe)]
        if futures:
            self.log_debug("Unsubscribing from %d futures", len(futures))
            for future in futures:
                self.unsubscribe(future)

    def __del__(self):
        # Unsubscribe from anything that is still active
        self.unsubscribe_all()

    def when_matches(self, path, good_value, bad_values=None, timeout=None):
        """Resolve when an path value equals value

        Args:
            path (list): The path to wait to
            good_value (object): the value to wait for
            bad_values (list): values to raise an error on
            timeout (float): time in seconds to wait for responses, wait
                forever if None
        """
        future = self.when_matches_async(path, good_value, bad_values)
        self.log_debug("Before")
        self.wait_all_futures(future, timeout)
        self.log_debug("After")

    def when_matches_async(self, path, good_value, bad_values=None):
        """Wait for an attribute to become a given value

        Args:
            path (list): The path to wait to
            good_value (object): the value to wait for
            bad_values (list): values to raise an error on

        Returns:
            Future: a single Future that will resolve when the path matches
                good_value or bad_values
        """
        def condition_satisfied(value):
            if bad_values and value in bad_values:
                raise BadValueError(
                    "Waiting for %r, got %r" % (good_value, value))
            return value == good_value

        when = When(condition_satisfied)
        future = self.subscribe(path, when.check_condition)
        when.set_future_context(future, weakref.proxy(self))
        return future

    def wait_all_futures(self, futures, timeout=None):
        """Services all futures until the list 'futures' are all done
        then returns. Calls relevant subscription callbacks as they
        come off the queue and raises an exception on abort

        Args:
            futures (Union[list, Future]): a future or list of all futures
                that the caller wants to wait for
            timeout (float): time in seconds to wait for responses, wait
                forever if None
        """
        if timeout is None:
            until = None
        else:
            until = time.time() + timeout

        if not isinstance(futures, list):
            futures = [futures]

        filtered_futures = []

        for f in futures:
            if f.done():
                if f.exception() is not None:
                    raise f.exception()
            else:
                filtered_futures.append(f)

        while filtered_futures:
            self._service_futures(filtered_futures, until)

    def sleep(self, seconds):
        """Services all futures while waiting

        Args:
            seconds (float): Time to wait
        """
        until = time.time() + seconds
        try:
            while True:
                self._service_futures([], until)
        except TimeoutError:
            return

    def _service_futures(self, futures, until=None):
        if until is None:
            timeout = None
        else:
            timeout = until - time.time()
            if timeout < 0:
                timeout = 0
        response = self._q.get(timeout)
        if response is self._sentinel_stop:
            self._sentinel_stop = None
        elif response is self.STOP:
            if self._sentinel_stop is None:
                # This is a stop we should listen to...
                raise AbortedError()
        elif isinstance(response, Update):
            # This is an update for a subscription
            (func, args) = self._subscriptions[response.id]
            func(response.value, *args)
        elif isinstance(response, Return):
            future = self._futures.pop(response.id)
            request = self._requests.pop(future)
            result = response.value
            # Deserialize if this was a method
            if isinstance(request, Post) and result is not None:
                controller = self.get_controller(request.path[0])
                result = controller.validate_result(request.path[1], result)
            future.set_result(result)
            if future in futures:
                futures.remove(future)
        elif isinstance(response, Error):
            future = self._futures.pop(response.id)
            del self._requests[future]
            future.set_exception(ResponseError(response.message))
            if future in futures:
                futures.remove(future)
                raise future.exception()