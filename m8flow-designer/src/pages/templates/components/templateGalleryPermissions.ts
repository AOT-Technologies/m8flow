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

/** A private template's creator manages it alongside the tenant-admin (M8F-712). */
function ownsPrivateTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  return template.visibility === 'PRIVATE' && !!actor.currentUsername && template.createdBy === actor.currentUsername;
}

export function canDeleteGalleryTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  if (actor.canDeleteTemplates === false || actor.canManageTemplates === false) return false;
  if (actor.isSuperAdmin) return false;
  if (template.isPublished) return actor.canManageTenant || ownsPrivateTemplate(template, actor);
  return actor.canManageTenant || (!!actor.currentUsername && template.createdBy === actor.currentUsername);
}

export function deleteDisabledReason(template: Template, actor: TemplateGalleryActor): string {
  if (actor.isSuperAdmin) return i18n.t('templates.notAvailableToSuperAdmin');
  if (template.isPublished && !actor.canManageTenant && !ownsPrivateTemplate(template, actor)) {
    return i18n.t('templates.permissions.deletePublished');
  }
  if (!actor.canManageTenant && actor.currentUsername !== template.createdBy) {
    return i18n.t('templates.permissions.deleteDraft');
  }
  return '';
}

export function canRestoreGalleryTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  if (actor.isSuperAdmin || actor.canRestoreTemplates === false) return false;
  return actor.canManageTenant || ownsPrivateTemplate(template, actor);
}
