from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "email" VARCHAR(255),
    "hashed_password" VARCHAR(255) NOT NULL,
    "preferred_wpm" INT NOT NULL,
    "created_at" TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_users_usernam_266d85" ON "users" ("username");
CREATE TABLE IF NOT EXISTS "saved_texts" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "title" VARCHAR(200) NOT NULL,
    "content" TEXT NOT NULL,
    "last_position" INT NOT NULL,
    "wpm" INT NOT NULL,
    "created_at" TIMESTAMP NOT NULL,
    "updated_at" TIMESTAMP NOT NULL,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztmVtv2jAUgP8KylMnbRPQ0lZ7SyldWVuYSrZVnSbLJCZYTZzUdkpRx3+f7STkzqDqGC"
    "DewrnYx5+dwznxi+Z6FnLYxwF8QpaBnrn2qfaiEegi8VBUvq9p0PcTlRRwOHSUNZNmgAs7"
    "JYdDxik05Ygj6DAkRBZiJsU+xx4RUhI4jhR6pjDExE5EAcGPAQLcsxEfIyoUP38JMSYWek"
    "Ys/uk/gBFGjpUJGVtybiUHfOorWZfwC2UoZxsC03MClyTG/pSPPTK3xkSt00YEUciRHJ7T"
    "QIYvo4sWG68ojDQxCUNM+VhoBAOHp5Y7BIlMA6DXN8CgYwCgrQDI9IiEK0JlavW2DOFDs3"
    "F0cnR6eHx0KkxUmHPJySycOgETOio8PUObKT3kMLRQjBOoHHMxXIFrewxpOdi5Q46tCDrP"
    "Nia5CG4sSOgmJ2odeF34DBxEbD6WTOv1BTC/67ftS/32QFi9k1N64hUIX49epGqGOkk8IS"
    "xm5Cg8eFnG8rUrZ5xy2QnKC6AanTtDjuwy9uikWR7c6HcKszuNNNf93ufYPMW+fd0/yyF3"
    "IOPA9xhWgS6fNAp+f88fb0W/vtH5I0E78d0VgEbW68N4WN8WkCZFcu0AlmSGc6Hh2EUV2S"
    "HjmWNrRa4f44ctTBeaWKDVJ840+q9dlD66N52Bod98zeSQc93oSE0zkz9i6cFxLn3PB6n9"
    "6BqXNfmzdt/vdRRej3GbqhkTO+NekzHBgHuAeBMArVRZEEtjapldD3zrlbue9dzv+qbses"
    "wote1R9KldZ4iClcrXlMf6kueGl7GyMRg9lFaxEleR7oVHEbbJFZoqyF0RESRmWfEadUPf"
    "omG2DO4sPj2xNElGFE7mnVT6UIm1ixUjHhb7+qCtn3c0RXgIzYcJpBbIoJYar+nlJHPbos"
    "ptunkJJNBWcOQqZMxp6iW9abwb1W2pXNC+Id2thlTuqXouoK3uSdM+b9Mw/V/Emaa0tUxP"
    "2qpuSVuFjhS5EDur8J07vApuhG5TsmWu5W+1lmn5W63qll/qsoDHkI1FqeZDxiYeLckS1a"
    "hLXHfiE8AaqPsUjRClgt5qTWrBb9+u7tvV3W9cqtrVQpldXRUmxyN3QZA9H2eR88XVLXJg"
    "xbe1sguJLTsIVXX47F9Wzzqi2BxrJfVzpFlYQcPEZl9C70oJ/SS6otIP39VlR8plX24sV2"
    "7Il2oFwpH5DtJtLHVr1lhwa9ZY4dbsy6DfW/XWzMImr/2uOZht8d9KGVwJY/HtWf6iLFcj"
    "yAHOyr6trfNT0OwPr6BqAw=="
)
