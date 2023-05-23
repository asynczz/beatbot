import db_handler
from os import remove
from glob import glob

beats = 3

chat_ids = db_handler.get_beats_generating_chat_ids()
mailing_list = []

for chat_id in chat_ids:
    for file in glob(f'output_beats/{chat_id}_[1-{beats}]*.wav'):
        remove(file)
    db_handler.del_beats_generating(chat_id)
    db_handler.del_processing(chat_id)
    mailing_list.append(chat_id)
    