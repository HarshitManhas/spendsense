"""Idempotently remove GridFS data referenced only by tombstoned receipts."""
from .database import database, files


def main():
    db, fs = database(), files()
    count = 0
    for row in db.receipts.find({'status': 'deleted'}):
        fs.delete(row['previewId'])
        if not db.receipts.count_documents({'ownerId': row['ownerId'], 'uploadId': row['uploadId'], 'status': {'$ne': 'deleted'}}):
            fs.delete(row['originalId'])
        count += 1
    print(f'Reconciled file cleanup for {count} deleted receipts.')


if __name__ == '__main__': main()
