import json
from pathlib import Path
from typing import Union

from desktop_env.eval.evaluator import Evaluator
from desktop_env.eval.google_evaluators.google_service import GoogleService


class GoogleCalendarService(GoogleService):
    def __init__(self, token_path: str) -> None:
        scopes = ["https://www.googleapis.com/auth/calendar"]
        super().__init__(
            scopes=scopes,
            token_path=token_path,
            service_name="calendar",
            service_version="v3",
        )

    def list_calendars(self) -> list[dict]:
        page_token = None
        calendar_entry_list = []
        while True:
            calendar_list = (
                self.service.calendarList().list(pageToken=page_token).execute()
            )
            for calendar_entry in calendar_list["items"]:
                calendar_entry_list.append(calendar_entry)

            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break
        return calendar_entry_list

    def create_event(
        self,
        summary: str | None,
        location: str | None,
        description: str | None,
        start_time: str,
        end_time: str,
        attendees: list[str] | None = None,
        calendar_id: str | None = "primary",
        time_zone: str | None = "UTC",
    ) -> dict[str, str]:
        event_info = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {
                "dateTime": start_time,
                "timeZone": time_zone,
            },
            "end": {
                "dateTime": end_time,
                "timeZone": time_zone,
            },
            "attendees": [{"email": attendee} for attendee in attendees]
            if attendees
            else [],
        }
        event = (
            self.service.events()
            .insert(calendarId=calendar_id, body=event_info)
            .execute()
        )
        return event

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return True
        except Exception as e:
            print(f"An error occurred: {e}")
            return False

    def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, str]:
        event = (
            self.service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
        return event

    def search_events(
        self, start_time: str, end_time: str, calendar_id: str = "primary"
    ) -> list[dict[str, str]]:
        events_result = (
            self.service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])


class GoogleCalendarEvaluator(Evaluator):
    @staticmethod
    def item_match(ref: str | None, pred: str | None) -> float:
        # print(f"ref: {ref}, pred: {pred}")
        return float(pred == ref)

    @staticmethod
    def list_match(ref: list, pred: list) -> float:
        score = 1.0
        for i in range(len(ref)):
            match_score = 0.0
            for j in range(len(pred)):
                if isinstance(ref[i], dict):
                    match_score = GoogleCalendarEvaluator.dict_match_left(
                        ref=ref[i], pred=pred[j]
                    )
                else:
                    match_score = GoogleCalendarEvaluator.item_match(
                        ref=ref[i], pred=pred[j]
                    )
                if match_score > 0.0:
                    break
            score *= match_score
        return score

    @staticmethod
    def dict_match_left(
        ref: Union[dict[str, str], dict[str, list], dict[str, dict]],
        pred: Union[dict[str, str], dict[str, list], dict[str, dict]],
    ) -> float:
        score = 1.0
        for key, item in ref.items():
            pred_item = pred.get(key, None)
            if isinstance(item, dict) and isinstance(pred_item, dict):
                score *= GoogleCalendarEvaluator.dict_match_left(
                    ref=item, pred=pred_item
                )
            elif isinstance(item, list) and isinstance(pred_item, list):
                score *= GoogleCalendarEvaluator.list_match(ref=item, pred=pred_item)
            elif isinstance(item, (str, int, float)) and isinstance(
                pred_item, (str, int, float)
            ):
                score *= GoogleCalendarEvaluator.item_match(ref=item, pred=pred_item)
            else:
                return 0.0
        return score

    def __call__(
        self,
        config_file: Path | str,
    ) -> float:
        with open(config_file, "r") as f:
            configs = json.load(f)

        score = 1.0
        gcalendar_service = GoogleCalendarService(token_path=configs["token_path"])

        try:
            for approach, value in configs["eval"]["reference_answers"].items():
                match approach:
                    case "event_match":
                        pred = gcalendar_service.search_events(
                            value["start"]["dateTime"], value["end"]["dateTime"]
                        )
                        if len(pred) == 0:
                            score = 0.0
                        elif len(pred) > 1:
                            raise ValueError(f"More than one event found: {pred}")
                        else:
                            score *= self.dict_match_left(value, pred[0])
        except Exception as e:
            print(f"An error occurred: {e}, score may be incorrect")
            score = 0.0

        return score