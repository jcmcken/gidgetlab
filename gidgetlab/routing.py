from typing import Any, Awaitable, Callable, Dict, List

from . import sansio


AsyncCallback = Callable[..., Awaitable[None]]


class Router:

    """Route webhook events to registered functions."""

    def __init__(self, *other_routers: "Router") -> None:
        """Instantiate a new router (possibly from other routers)."""
        self._shallow_routes: Dict[str, List[AsyncCallback]] = {}
        # event type -> data key -> data value -> callbacks
        self._deep_routes: Dict[str, Dict[str, Dict[Any, List[AsyncCallback]]]] = {}
        for other_router in other_routers:
            for event_type, callbacks in other_router._shallow_routes.items():
                for callback in callbacks:
                    self.add(callback, event_type)
            for event_type, object_attributes in other_router._deep_routes.items():
                for data_key, data_specifics in object_attributes.items():
                    for data_value, callbacks in data_specifics.items():
                        detail = {data_key: data_value}
                        for callback in callbacks:
                            self.add(callback, event_type, **detail)

    def add(
        self, func: AsyncCallback, event_type: str, **object_attribute: Any
    ) -> None:
        """Add a new route.

        After registering 'func' for the specified event_type, an
        optional object_attribute may be provided. By providing an extra
        keyword argument, dispatching can occur based on a key from the
        object_attributes dict of the data in the event being dispatched.
        """
        if len(object_attribute) > 1:
            raise TypeError(
                "dispatching based on object attributes is only "
                "supported up to one level deep; "
                f"{len(object_attribute)} levels specified"
            )
        elif not object_attribute:
            callbacks = self._shallow_routes.setdefault(event_type, [])
            callbacks.append(func)
        else:
            data_key, data_value = object_attribute.popitem()
            object_attributes = self._deep_routes.setdefault(event_type, {})
            specific_detail = object_attributes.setdefault(data_key, {})
            callbacks = specific_detail.setdefault(data_value, [])
            callbacks.append(func)

    def register(
        self, event_type: str, **object_attribute: Any
    ) -> Callable[[AsyncCallback], AsyncCallback]:
        """Decorator to apply the add() method to a function."""

        def decorator(func: AsyncCallback) -> AsyncCallback:
            self.add(func, event_type, **object_attribute)
            return func

        return decorator

    async def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event to all registered function(s)."""

        found_callbacks = []
        try:
            found_callbacks.extend(self._shallow_routes[event.event])
        except KeyError:
            pass
        try:
            details = self._deep_routes[event.event]
        except KeyError:
            pass
        else:
            for data_key, data_values in details.items():
                if data_key in event.object_attributes:
                    event_value = event.object_attributes[data_key]
                    if event_value in data_values:
                        found_callbacks.extend(data_values[event_value])
        for callback in found_callbacks:
            await callback(event, *args, **kwargs)
