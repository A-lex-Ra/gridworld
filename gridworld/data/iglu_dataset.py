import os
import json
import pandas as pd
import numpy as np
from collections import defaultdict
from ..tasks.task import Subtasks, Task, Tasks


VOXELWORLD_GROUND_LEVEL = 63

block_colour_map = {
    # voxelworld's colour id : iglu colour id
    0: 0,  # air
    57: 1, # blue
    50: 2, # yellow
    59: 3, # green
    47: 4, # orange
    56: 5, # purple
    60: 6  # red
}

def fix_xyz(x, y, z):
    XMAX = 11
    YMAX = 9
    ZMAX = 11
    COORD_SHIFT = [5, -63, 5]

    x += COORD_SHIFT[0]
    y += COORD_SHIFT[1]
    z += COORD_SHIFT[2]

    index = z + y * YMAX + x * YMAX * ZMAX
    new_x = index // (YMAX * ZMAX)
    index %= (YMAX * ZMAX)
    new_y = index // ZMAX
    index %= ZMAX
    new_z = index % ZMAX

    new_x -= COORD_SHIFT[0]
    new_y -= COORD_SHIFT[1]
    new_z -= COORD_SHIFT[2]

    return new_x, new_y, new_z

def fix_log(log_string):
    """
    log_string: str
        log_string should be a string of the full log.
        It should be multiple lines, each corresponded to a timestamp,
        and should be separated by newline character.    
    """

    lines = []

    for line in log_string.splitlines():

        if "block_change" in line:
            line_splits = line.split(" ", 2)
            try:
                info = eval(line_splits[2])
            except:
                lines.append(line)
                continue
            x, y, z = info[0], info[1], info[2]
            new_x, new_y, new_z = fix_xyz(x, y, z)
            new_info = (new_x, new_y, new_z, info[3], info[4])
            line_splits[2] = str(new_info)
            fixed_line = " ".join(line_splits)
            # logging.info(f"Fixed {line} to {fixed_line}")

            lines.append(fixed_line)
        else:
            lines.append(line)

    return "\n".join(lines)

class IGLUDataset(Tasks):
    def __init__(self, task_kwargs=None) -> None:
        # assume we downloaded it. add this later
        if task_kwargs is None:
            task_kwargs = {}
        self.task_kwargs = task_kwargs
        path = './raw'
        dialogs = pd.read_csv(f'{path}/HitsTable2.csv')
        self.tasks = defaultdict(list)
        self.parse_tasks(dialogs, path)
        pass
    
    def parse_tasks(self, dialogs, path):
        for sess_id, gr in dialogs.groupby('PartitionKey'):
            utt_seq = []
            blocks = []
            if not os.path.exists(f'{path}/builder-data/{sess_id}'):
                continue
            assert len(gr.structureId.unique()) == 1
            structure_id = gr.structureId.values[0]
            for i, row in gr.sort_values('StepId').reset_index(drop=True).iterrows():
                if row.StepId % 2 == 1:
                    if isinstance(row.instruction, str):
                        utt_seq.append([])
                        utt_seq[-1].append(row.instruction)
                    elif isinstance(row.Answer4ClarifyingQuestion, str):
                        utt_seq[-1].append(row.Answer4ClarifyingQuestion)
                else:
                    if isinstance(row.ClarifyingQuestion, str):
                        utt_seq[-1].append(row.ClarifyingQuestion)
                        continue
                    blocks.append([])
                    curr_step = f'{path}/builder-data/{sess_id}/step-{row.StepId}'
                    if not os.path.exists(curr_step):
                        continue
                    with open(curr_step) as f:
                        step_data = json.load(f)
                    for x, y, z, bid in step_data['worldEndingState']['blocks']:
                        y = y - VOXELWORLD_GROUND_LEVEL - 1
                        bid = block_colour_map.get(bid, 5) # TODO: some blocks have id 1, check why
                        blocks[-1].append((x, y, z, bid))
            i = 0
            while i < len(blocks):
                if len(blocks[i]) == 0:
                    if i == len(blocks) - 1:
                        blocks = blocks[:i]
                        utt_seq = utt_seq[:i]
                    else:
                        blocks = blocks[:i] + blocks[i + 1:]
                        utt_seq[i] = utt_seq[i] + utt_seq[i + 1]
                        utt_seq = utt_seq[:i + 1] + utt_seq[i + 2:] 
                i += 1
            if len(blocks) > 0:
                task = Subtasks(utt_seq, blocks, **self.task_kwargs)
                self.tasks[structure_id].append(task)
    
    def reset(self):
        sample = np.random.choice(list(self.tasks.keys()))
        sess_id = np.random.choice(len(self.tasks[sample]))
        self.current = self.tasks[sample][sess_id]
        return self.current
    
    def __len__(self):
        return sum(len(sess.structure_seq) for sess in sum(self.tasks.values(), []))

    def __iter__(self):
        for task_id, tasks in self.tasks.items():
            for j, task in enumerate(tasks):
                for subtask in task:
                    yield task_id, j, subtask


iglu_data = IGLUDataset()
print(iglu_data)  
print(f'total structures: {len(iglu_data.tasks)}')
print(f'total sessions: {len(sum(iglu_data.tasks.values(), []))}')
print(f'total total RL tasks: {sum(len(sess.structure_seq) for sess in sum(iglu_data.tasks.values(), []))}')
print()