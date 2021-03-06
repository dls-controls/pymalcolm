from malcolm.yamlutil import check_yaml_names, make_block_creator

hdf_writer_block = make_block_creator(__file__, "hdf_writer_block.yaml")
position_labeller_block = make_block_creator(__file__, "position_labeller_block.yaml")
stats_plugin_block = make_block_creator(__file__, "stats_plugin_block.yaml")
ffmpeg_plugin_block = make_block_creator(__file__, "ffmpeg_plugin_block.yaml")

__all__ = check_yaml_names(globals())
