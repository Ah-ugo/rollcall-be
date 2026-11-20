import io, csv
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..core.database import db
from ..core.security import current_lecturer, owned_class
from .attendance import session_status

router = APIRouter(prefix="/classes", tags=["reports"])

async def build(c):
    sessions = [s async for s in db.attendance_sessions.find({"class_id": c["_id"], "cancelled": False}).sort("start_time", 1)]
    eligible = [s for s in sessions if session_status(s) in ("ended", "closed", "open")]
    recs = {}
    async for r in db.attendance_records.find({"class_id": c["_id"]}):
        recs.setdefault(r["enrollment_id"], set()).add(r["session_id"])
    elig_ids = {s["_id"] for s in eligible}
    rows = []
    async for e in db.class_enrollments.find({"class_id": c["_id"]}).sort("full_name", 1):
        att = len(recs.get(e["_id"], set()) & elig_ids)
        tot = len(eligible)
        rows.append({"full_name": e["full_name"], "matric_no": e["matric_no"], "total": tot, "attended": att,
                     "absent": tot - att, "percentage": round(100 * att / tot, 1) if tot else 0.0})
    per_session = []
    for s in eligible:
        p = await db.attendance_records.count_documents({"session_id": s["_id"]})
        f = await db.attendance_attempts.count_documents({"session_id": s["_id"], "success": False})
        per_session.append({"id": str(s["_id"]), "title": s["title"], "date": s["start_time"].strftime("%Y-%m-%d"),
                            "present": p, "absent": len(rows) - p, "failed_attempts": f})
    return {"students": rows, "sessions": per_session, "total_sessions": len(eligible)}

@router.get("/{class_id}/report")
async def report(class_id: str, lec=Depends(current_lecturer)):
    return await build(await owned_class(class_id, lec))

@router.get("/{class_id}/report/export")
async def export(class_id: str, format: str = "csv", lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    data = await build(c)
    head = ["Name", "Matric no.", "Sessions", "Attended", "Absent", "Attendance %"]
    rows = [[r["full_name"], r["matric_no"], r["total"], r["attended"], r["absent"], r["percentage"]] for r in data["students"]]
    name = f'{c["course_code"].replace(" ", "_")}_attendance'
    if format == "xlsx":
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "Students"
        ws.append(head); [ws.append(r) for r in rows]
        ws2 = wb.create_sheet("Sessions"); ws2.append(["Session", "Date", "Present", "Absent", "Failed attempts"])
        [ws2.append([s["title"], s["date"], s["present"], s["absent"], s["failed_attempts"]]) for s in data["sessions"]]
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    if format == "pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        buf = io.BytesIO(); st = getSampleStyleSheet()
        t = Table([head] + rows, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F8")])]))
        SimpleDocTemplate(buf, pagesize=A4).build([Paragraph(f'{c["course_code"]} – {c["course_title"]}', st["Title"]),
            Paragraph(f'Attendance report · {data["total_sessions"]} sessions', st["Normal"]), Spacer(1, 12), t])
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(head); w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
