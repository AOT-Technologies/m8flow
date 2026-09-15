import type { Template } from '@/lib/templatesApi';

export type TemplateGalleryMode = 'active' | 'deleted';

export type TemplateGalleryActor = {
  isSuperAdmin: boolean;
  /** Tenant-admin of the active tenant — not super-admin (read-only). */
  canManageTenant: boolean;
  currentUsername: string | null;
};

export function canDeleteGalleryTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  if (actor.isSuperAdmin) return false;
  if (template.isPublished) return actor.canManageTenant;
  return actor.canManageTenant || (!!actor.currentUsername && template.createdBy === actor.currentUsername);
}

export function deleteDisabledReason(template: Template, actor: TemplateGalleryActor): string {
  if (actor.isSuperAdmin) return 'Not available to super-admin';
  if (template.isPublished && !actor.canManageTenant) {
    return 'Insufficient permissions to delete published templates.';
  }
  if (!actor.canManageTenant && actor.currentUsername !== template.createdBy) {
    return 'Only the template creator or an admin can delete this draft template.';
  }
  return '';
}

export function canRestoreGalleryTemplate(actor: TemplateGalleryActor): boolean {
  return !actor.isSuperAdmin && actor.canManageTenant;
}
