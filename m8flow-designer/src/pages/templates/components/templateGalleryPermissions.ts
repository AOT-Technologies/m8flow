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
  /** Cookie-authoritative active tenant (`useActiveTenant().activeTenantId`). */
  activeTenantId: string | null;
};

/** PUBLIC templates from another tenant are readable here but never manageable. */
export function isActiveTenantTemplate(template: Template, activeTenantId: string | null | undefined): boolean {
  return !!activeTenantId && template.tenantId === activeTenantId;
}

/** A private template's creator manages it alongside the tenant-admin. */
function ownsPrivateTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  return template.visibility === 'PRIVATE' && !!actor.currentUsername && template.createdBy === actor.currentUsername;
}

export function canDeleteGalleryTemplate(template: Template, actor: TemplateGalleryActor): boolean {
  if (actor.canDeleteTemplates === false || actor.canManageTemplates === false) return false;
  if (actor.isSuperAdmin) return false;
  if (!isActiveTenantTemplate(template, actor.activeTenantId)) return false;
  if (template.isPublished) return actor.canManageTenant || ownsPrivateTemplate(template, actor);
  return actor.canManageTenant || (!!actor.currentUsername && template.createdBy === actor.currentUsername);
}

export function deleteDisabledReason(template: Template, actor: TemplateGalleryActor): string {
  if (actor.isSuperAdmin) return i18n.t('templates.notAvailableToSuperAdmin');
  if (!isActiveTenantTemplate(template, actor.activeTenantId)) return i18n.t('templates.permissions.otherTenant');
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
  if (!isActiveTenantTemplate(template, actor.activeTenantId)) return false;
  return actor.canManageTenant || ownsPrivateTemplate(template, actor);
}
