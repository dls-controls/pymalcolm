from malcolm.core.meta import Meta
from malcolm.core.serializable import Serializable

@Serializable.register("malcolm:core/BlockMeta:1.0")
class BlockMeta(Meta):
    pass
