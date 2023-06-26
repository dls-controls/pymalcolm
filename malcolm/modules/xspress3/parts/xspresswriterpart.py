import os
from typing import Dict, Iterator, List, Optional

import h5py
from annotypes import Anno, add_call_types
from numpy import block
from scanpointgenerator import CompoundGenerator
from vdsgen import InterleaveVDSGenerator, ReshapeVDSGenerator

from malcolm.core import APartName, BadValueError, Future, Info, PartRegistrar
from malcolm.modules import builtin, scanning

PartInfo = Dict[str, List[Info]]

# If the HDF writer doesn't get new frames in this time (seconds), consider it
# stalled and raise
FRAME_TIMEOUT = 60

# Pull re-used annotypes into our namespace in case we are subclassed
APartName = APartName
AMri = builtin.parts.AMri
AInitialVisibility = builtin.parts.AInitialVisibility

with Anno("name of sum dataset"):
    ASumName = str
with Anno("name of secondary dataset (e.g. sum)"):
    ASecondaryDataset = str
with Anno("number of FR/FP pairs"):
    ANumberPairs = int

dict_filewriter = ['A','B','C','D','E','F','G','H']

def greater_than_zero(v: int) -> bool:
    return v > 0


def create_dataset_infos(
    name: str, generator: CompoundGenerator, filename: str, secondary_set: str
) -> Iterator[Info]:
    # Update the dataset tableExternalLink
    generator_rank = len(generator.dimensions)
    # Add the primary datasource
    yield scanning.infos.DatasetProducedInfo(
        name=f"{name}.data",
        filename=filename,
        type=scanning.infos.DatasetType.PRIMARY,
        rank=generator_rank + 2,
        path="/entry/xspress/data",
        uniqueid="/entry/xspress/uid",
    )


    # Add any setpoint dimensions
    for dim in generator.axes:
        yield scanning.infos.DatasetProducedInfo(
            name=f"{dim}.value_set",
            filename=filename,
            type=scanning.infos.DatasetType.POSITION_SET,
            rank=1,
            path=f"/entry/xspress/{dim}_set",
            uniqueid="",
        )



def create_raw_dataset_infos(
    name: str,
    rank: int,
    filename: str,
    n_raw: int
) -> Iterator[Info]:
    for i in range(8): #change this to be realted to the number of channels
        yield scanning.infos.DatasetProducedInfo(
            name=f"{name}.raw_mca{i}",
            filename=filename,
            type=scanning.infos.DatasetType.RAW,
            rank=rank,
            path="/raw/mca" + str(i),
            uniqueid=""
        )
        yield scanning.infos.DatasetProducedInfo(
            name=f"{name}.dtc_chan{i}",
            filename=filename,
            type=scanning.infos.DatasetType.RAW,
            rank=rank,
            path="/raw/dtc_chan" + str(i),
            uniqueid="",
        )
        yield scanning.infos.DatasetProducedInfo(
            name=f"{name}.scalar_chan{i}",
            filename=filename,
            type=scanning.infos.DatasetType.RAW,
            rank=rank,
            path="/raw/scalar_chan" + str(i),
            uniqueid="",
        )


def files_shape(frames, block_size, file_count):
    print('file shape based on {} frames with a {} block size and a {} file count.'.format(frames,block_size,file_count))
    # all files get at least per_file blocks
    per_file = int(frames) / int(file_count * block_size)
    # this is the remainder once per_file blocks have been distributed
    remainder = int(frames) % int(file_count * block_size)

    # distribute the remainder
    remainders = [
        block_size if remains > block_size else remains
        for remains in range(remainder, 0, -block_size)
    ]
    # pad the remainders list with zeros
    remainders += [0] * (file_count - len(remainders))

    shape = tuple(int(per_file * block_size + remainders[i]) for i in range(file_count))
    return shape


def one_vds(
    vds_folder,
    vds_name,
    files,
    width,
    height,
    shape,
    generator,
    alternates,
    block_size,
    source_node,
    target_node,
    d_type,
):
    # this vds reshapes from 1 file per data writer to a single 1D data set
    gen = InterleaveVDSGenerator(
        vds_folder,
        files=files,
        source={"height": width, "width": height, "dtype": d_type, "shape": shape},
        output=vds_name,
        source_node=source_node,
        target_node="process/" + target_node + "_interleave",
        block_size=block_size,
        log_level=1,
    )
    gen.generate_vds()
    
    # this VDS shapes the data to match the dimensions of the scan
    gen = ReshapeVDSGenerator(
        path=vds_folder,
        files=[vds_name],
        source_node="process/" + target_node + "_interleave",
        target_node=target_node,
        output=vds_name,
        shape=generator.shape,
        alternate=alternates,
        log_level=1,
    )

    gen.generate_vds()


def create_vds(generator, raw_name, vds_path, child, sum_name):
    vds_folder, vds_name = os.path.split(vds_path)
    image_width = int(child.imageWidth.value)
    image_height = int(child.imageHeight.value)
    block_size = int(child.blockSize.value)
    hdf_count = int(child.numProcesses.value)
    data_type = str(child.dataType.value)

    # hdf_shape tuple represents the number of images in each file
    hdf_shape = files_shape(generator.size, block_size, hdf_count)

    # The first dimension alternating has no meaning. If any subsequent ones
    # alternate then it will radically slow down the VDS creation and reading.
    # We rely on a scanning.parts.UnrollingPart to
    if any(dim.alternate for dim in generator.dimensions[1:]):
        raise BadValueError(
            "Snake scans are not supported as the VDS is not performant. You "
            "can add a scanning.parts.UnrollingPart to the top level scan "
            "block to unroll the scan into one long line"
        )
    alternates = None
    
    files = [
        os.path.join(vds_folder, f"{raw_name}_{dict_filewriter[i]}_{0:06d}.h5") for i in range(hdf_count)
    ]

    metafile = os.path.join(vds_folder,f"{raw_name}_meta.h5")
    

    shape = (hdf_shape, image_height, image_width)
    print('shape: {}'.format(shape))
    # prepare a vds for the image data
    one_vds(
        vds_folder,
        vds_name,
        files,
        1,
        image_height,
        shape,
        generator,
        alternates,
        block_size,
        "data",
        "data",
        data_type.lower(),
    )
    with h5py.File(vds_path, "r+", libver="latest") as vds:
        count = 1
        for i in range(8): #add a more generic way of running through the number of channels
            vds['raw/dtc_chan' + str(i)] = h5py.ExternalLink(metafile, "/dtc_chan{}".format(str(i)))
            vds['raw/scalar_chan' + str(i)] = h5py.ExternalLink(metafile, "/scalar_chan{}".format(str(i)))
        for f in files:
            print("Filename: {}".format(f))
            vds['raw/mca' + str(4*count-4)] = h5py.ExternalLink(f, "/mca_{}".format(str(4*count-4)))
            vds['raw/mca' + str(4*count-3)] = h5py.ExternalLink(f, "/mca_{}".format(str(4*count-3)))
            vds['raw/mca' + str(4*count-2)] = h5py.ExternalLink(f, "/mca_{}".format(str(4*count-2)))
            vds['raw/mca' + str(4*count-1)] = h5py.ExternalLink(f, "/mca_{}".format(str(4*count-1)))
            count += 1

    shape = (hdf_shape, 1, 1)



set_bases = ["/entry/xspress/"]
set_data = ["/data"]


def add_nexus_nodes(generator, vds_file_path):
    """Add in the additional information to make this into a standard nexus
    format file:-
    (a) create the standard structure under the 'entry' group with a
    subgroup for each dataset. 'set_bases' lists the data sets we make here.
    (b) save a dataset for each axis in each of the dimensions of the scan
    representing the demand position at every point in the scan.
    """

    # create the axes dimensions attribute, a comma separated list giving size
    # of the axis dimensions padded with . for the detector dimensions and
    # multidimensional dimensions
    pad_dims = []
    for d in generator.dimensions:
        if len(d.axes) == 1:
            pad_dims.append(f"{d.axes[0]}_set")
        else:
            pad_dims.append(".")

    pad_dims += ["."] * 2  # assume a 2 dimensional detector | is xspress a 2 dimensional detector?

    with h5py.File(vds_file_path, "r+", libver="latest") as vds:
        for data, node in zip(set_data, set_bases):
            # create a group for this entry
            vds.require_group(node)
            # points to the axis demand data sets
            vds[node].attrs["axes"] = pad_dims
            vds[node].attrs["NX_class"] = ["NXdata"]

            # points to the detector dataset for this entry
            vds[node].attrs["signal"] = data.split("/")[-1]
            # a hard link from this entry 'signal' to the actual data
            vds[node + data] = vds[data]

            axis_sets = {}
            # iterate the axes in each dimension of the generator to create the
            # axis information nodes
            for i, d in enumerate(generator.dimensions):
                for axis in d.axes:
                    # add signal data dimension for axis
                    axis_indices = f"{axis}_set_indices"
                    vds[node].attrs[axis_indices] = i

                    # demand positions for axis
                    axis_set = f"{axis}_set"
                    if axis_sets.get(axis_set):
                        # link to the first entry's demand list
                        vds[node + axis_set] = axis_sets[axis_set]
                    else:
                        # create the demand list for the first entry only
                        axis_demands = d.get_positions(axis)
                        vds.create_dataset(node + axis_set, data=axis_demands)
                        vds[node + axis_set].attrs["units"] = generator.units[axis]
                    axis_sets[axis_set] = vds[node + axis_set]

        vds["entry"].attrs["NX_class"] = ["NXentry"]


# We will set these attributes on the child block, so don't save them
@builtin.util.no_save("fileName", "filePath", "numCapture","chunkSize")
class XspressWriterPart(builtin.parts.ChildPart):
    """Part for controlling an `xspress3_writer_block` in a Device"""

    # Future for the start action
    start_future: Optional[Future] = None
    unique_id_offset: int = 0
    # The HDF5 layout file we write to say where the datasets go
    layout_filename: str = ""
    exposure_time: float = 0.0

    def __init__(
        self,
        name: APartName,
        mri: AMri,
        initial_visibility: AInitialVisibility = True,
        sum_name: ASumName = "sum",
        secondary_set: ASecondaryDataset = "sum",
        num_pairs: ANumberPairs = 1,
    ) -> None:
        self.sum_name = sum_name
        self.secondary_set = secondary_set
        self.num_pairs = num_pairs
        super().__init__(name, mri, initial_visibility)

    @add_call_types
    def on_reset(self, context: scanning.hooks.AContext) -> None:
        super().on_reset(context)
        self.on_abort(context)

    def setup(self, registrar: PartRegistrar) -> None:
        super().setup(registrar)
        # Tell the controller to expose some extra configure parameters
        registrar.report(scanning.hooks.ConfigureHook.create_info(self.on_configure))
        # Hooks
        registrar.hook(scanning.hooks.ConfigureHook, self.on_configure)
        registrar.hook(scanning.hooks.SeekHook, self.on_seek)
        registrar.hook(scanning.hooks.RunHook, self.on_run)
        registrar.hook(scanning.hooks.PostRunArmedHook, self.on_post_run_armed)
        registrar.hook(scanning.hooks.PostRunReadyHook, self.on_post_run_ready)
        registrar.hook(scanning.hooks.AbortHook, self.on_abort)
        registrar.hook(scanning.hooks.PauseHook, self.on_pause)

    @add_call_types
    def on_pause(self, context: scanning.hooks.AContext) -> None:
        raise NotImplementedError("Pause not implemented")

    # Allow CamelCase as these parameters will be serialized
    # noinspection PyPep8Naming
    @add_call_types
    def on_configure(
        self,
        context: scanning.hooks.AContext,
        completed_steps: scanning.hooks.ACompletedSteps,
        steps_to_do: scanning.hooks.AStepsToDo,
        generator: scanning.hooks.AGenerator,
        fileDir: scanning.hooks.AFileDir,
        formatName: scanning.hooks.AFormatName = "xspress3",
        fileTemplate: scanning.hooks.AFileTemplate = "%s.h5",
    ) -> scanning.hooks.UInfos:

        self.exposure_time = generator.duration
        # On initial configure, expect to get the demanded number of frames
        self.done_when_reaches = completed_steps + self.num_pairs*steps_to_do

        self.unique_id_offset = 0
        child = context.block_view(self.mri)
        file_dir = fileDir.rstrip(os.sep)

        chunk = int(1/float(self.exposure_time))
        if(chunk < 1):
            chunk=1
        if(chunk > 1024):
            chunk=1024
        # print("new chunkSize value: {}".format(chunk))
        child.chunkSize.put_value(chunk)
        # derive file path from template as AreaDetector would normally do
        fileName = fileTemplate.replace("%s", formatName)

        # this is path to the requested file which will be a VDS
        vds_full_filename = os.path.join(fileDir, fileName)

        # this is the path to underlying file the xspress3 writer will write to
        raw_file_name = fileTemplate.replace("%s", formatName + "_raw_data")
        raw_file_basename, _ = os.path.splitext(raw_file_name)

        assert (
            "." in vds_full_filename
        ), f"File extension for {vds_full_filename!r} should be supplied"
        futures = child.put_attribute_values_async(
            dict(
                numCapture=generator.size,
                filePath=file_dir + os.sep,
                fileName=raw_file_basename,
            )
        )
        context.wait_all_futures(futures)

        # Start the plugin
        self.start_future = child.start_async()
        # Start a future waiting for the first array
        self.array_future = child.when_value_matches_async(
            "numCaptured", greater_than_zero
        )

        create_vds(
            generator,
            raw_file_basename,
            vds_full_filename,
            child,
            self.sum_name,
        )
        add_nexus_nodes(generator, vds_full_filename)

        # Return the dataset information
        dataset_infos = list(
            create_dataset_infos(formatName, generator, fileName, self.secondary_set)
        )
        raw_file_names = [
            f"{raw_file_basename}_{dict_filewriter[i]}_{0:06d}.h5"
            for i in range(int(child.numProcesses.value))
        ]
        raw_file_names += [f"{raw_file_basename}_meta.h5"]
        dataset_infos += list(
            create_raw_dataset_infos(
                formatName, len(generator.dimensions) + 2, fileName, int(child.numProcesses.value)
            )
        )

        return dataset_infos

    @add_call_types
    def on_seek(
        self,
        context: scanning.hooks.AContext,
        completed_steps: scanning.hooks.ACompletedSteps,
        steps_to_do: scanning.hooks.AStepsToDo,
    ) -> None:
        # This is rewinding or setting up for another batch, so the detector
        # will skip to a uniqueID that has not been produced yet
        self.unique_id_offset = completed_steps - self.done_when_reaches
        self.done_when_reaches += steps_to_do
        child = context.block_view(self.mri)
        # Just reset the array counter_block
        child.arrayCounter.put_value(0)
        # Start a future waiting for the first array
        self.array_future = child.when_value_matches_async(
            "numCaptured", greater_than_zero
        )

    @add_call_types
    def on_run(self, context: scanning.hooks.AContext) -> None:
        context.wait_all_futures(self.array_future)
        context.unsubscribe_all()
        child = context.block_view(self.mri)
        child.numCaptured.subscribe_value(self.update_completed_steps)
        child.when_value_matches(
            "numCaptured",
            self.done_when_reaches,
            event_timeout=self.exposure_time + FRAME_TIMEOUT,
        )

    @add_call_types
    def on_post_run_armed(
        self,
        context: scanning.hooks.AContext,
        steps_to_do: scanning.hooks.AStepsToDo,
    ) -> None:
        self.done_when_reaches += steps_to_do

    @add_call_types
    def on_post_run_ready(self, context: scanning.hooks.AContext) -> None:
        # If this is the last one, wait until the file is closed
        context.wait_all_futures(self.start_future)

    @add_call_types
    def on_abort(self, context: scanning.hooks.AContext) -> None:
        child = context.block_view(self.mri)
        child.stop()

    def update_completed_steps(self, value: int) -> None:
        completed_steps = value + self.unique_id_offset
        # print('completed_steps = {}'.format(completed_steps))
        assert self.registrar, "No registrar"
        self.registrar.report(scanning.infos.RunProgressInfo(completed_steps))
