import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";

const updateSchema = z.object({
  completed: z.boolean(),
});

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await request.json();
  const parsed = updateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }
  // pretend DB call
  return NextResponse.json({ id: params.id, completed: parsed.data.completed });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  // pretend DB call
  return NextResponse.json({ id: params.id, deleted: true });
}
