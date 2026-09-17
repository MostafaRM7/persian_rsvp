from tortoise import fields, models


class User(models.Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=50, unique=True, db_index=True)
    email = fields.CharField(max_length=255, null=True)
    hashed_password = fields.CharField(max_length=255)
    preferred_wpm = fields.IntField(default=300)
    pause_intensity = fields.FloatField(default=1.0)
    difficulty_tolerance = fields.FloatField(default=0.0)
    personalization_enabled = fields.BooleanField(default=True)
    plan_tier = fields.CharField(max_length=20, default="free")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return self.username


class SavedText(models.Model):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="saved_texts", on_delete=fields.CASCADE)
    title = fields.CharField(max_length=200)
    content = fields.TextField()
    last_position = fields.IntField(default=0)
    wpm = fields.IntField(default=300)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "saved_texts"

    def __str__(self) -> str:
        return self.title


class UsageRecord(models.Model):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="usage_records", null=True, on_delete=fields.SET_NULL)
    identifier = fields.CharField(max_length=100, db_index=True)
    tokens_count = fields.IntField()
    endpoint = fields.CharField(max_length=50, default="/api/rsvp/plan")
    created_at = fields.DatetimeField(auto_now_add=True, db_index=True)

    class Meta:
        table = "usage_records"

    def __str__(self) -> str:
        return f"{self.identifier}: {self.tokens_count} tokens"

