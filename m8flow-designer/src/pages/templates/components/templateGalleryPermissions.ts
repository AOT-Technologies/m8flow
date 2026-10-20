import i18n from '@/i18n';
import type { Template } from '@/lib/templatesApi';

export type TemplateGalleryMode = 'active' | 'deleted';

export type TemplateGalleryActor = {
  canManageTemplates?: boolean;
  canImportTemplates?: boolean;
  canDeleteTemplates?: boolean;
  canRestoreTemplates?: boolean;
  isSuperAdmin: boolean;
  /** Tenant-admin of the active tenant — not super-admin (read-only). */
  canManageTenant: boolean;
  currentUsername: string | null;
};

export function canDeleteGalleryTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  if (actor.canDeleteTemplates === false || actor.canManageTemplates === false) return false;
  if (actor.isSuperAdmin) return false;
  if (template.isPublished) return actor.canManageTenant;
  return actor.canManageTenant || (!!actor.currentUsername && template.createdBy === actor.currentUsername);
}

export function deleteDisabledReason(template: Template, actor: TemplateGalleryActor): string {
  if (actor.isSuperAdmin) return i18n.t('templates.notAvailableToSuperAdmin');
  if (template.isPublished && !actor.canManageTenant) {
    return i18n.t('templates.permissions.deletePublished');
  }
  if (!actor.canManageTenant && actor.currentUsername !== template.createdBy) {
    return i18n.t('templates.permissions.deleteDraft');
  }
  return '';
}

export function canRestoreGalleryTemplate(actor: TemplateGalleryActor): boolean {
  return !actor.isSuperAdmin && actor.canManageTenant && actor.canRestoreTemplates !== false;
}
