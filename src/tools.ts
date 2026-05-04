import type {
  AgentDecision,
  Appointment,
  Conversation,
  Repository,
  Tenant,
} from "./types";

export async function executeTool(input: {
  decision: AgentDecision;
  tenant: Tenant;
  conversation: Conversation;
  contactWaId: string;
  repository: Repository;
}): Promise<{ reply: string; toolResult?: unknown }> {
  const tool = input.decision.tool ?? { name: "none", arguments: {} };
  const args = tool.arguments ?? {};

  if (tool.name === "list_services") {
    const services = input.tenant.services.length
      ? input.tenant.services.join(", ")
      : "Por ahora no tengo una lista cerrada de servicios.";

    return {
      reply: input.decision.reply || `Estos son los servicios disponibles: ${services}.`,
      toolResult: { services: input.tenant.services },
    };
  }

  if (tool.name === "create_appointment") {
    const appointment = await input.repository.createAppointment({
      tenant: input.tenant,
      conversation: input.conversation,
      contactWaId: input.contactWaId,
      customerName: readString(args.customerName),
      serviceName: readString(args.serviceName),
      requestedDateText: readString(args.requestedDateText),
      scheduledAt: parsePossibleDate(readString(args.requestedDateText)),
      notes: readString(args.notes),
    });

    return {
      reply: withAppointmentSafety(input.decision.reply, appointment),
      toolResult: appointment,
    };
  }

  if (tool.name === "cancel_appointment") {
    const cancelled = await input.repository.cancelLatestAppointment({
      tenant: input.tenant,
      conversation: input.conversation,
      requestedDateText: readString(args.requestedDateText),
      notes: readString(args.notes),
    });

    if (!cancelled) {
      return {
        reply:
          "No encontre una cita activa con esos datos. Puedes decirme el dia y la hora de la cita que quieres cancelar?",
        toolResult: { cancelled: false },
      };
    }

    return {
      reply:
        input.decision.reply ||
        "Listo, deje registrada la cancelacion de esa cita.",
      toolResult: cancelled,
    };
  }

  return {
    reply: input.decision.reply,
  };
}

function withAppointmentSafety(reply: string, appointment: Appointment): string {
  if (reply.trim()) {
    return reply;
  }

  const when = appointment.requestedDateText
    ? ` para ${appointment.requestedDateText}`
    : "";
  return `Perfecto, deje registrada tu solicitud de cita${when}.`;
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parsePossibleDate(value: string | null): Date | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}
