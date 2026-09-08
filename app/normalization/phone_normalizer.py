import phonenumbers


class PhoneNormalizer:
    @staticmethod
    def normalize(phone_str: str, default_region: str = "AZ") -> str | None:
        try:
            parsed = phonenumbers.parse(phone_str, default_region)
        except phonenumbers.NumberParseException:
            return None
        return (
            phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            if phonenumbers.is_valid_number(parsed)
            else None
        )
