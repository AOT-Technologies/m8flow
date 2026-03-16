import { Template } from '../types/template';

interface CuratedTemplatesSectionProps {
  templates: Template[];
  onUseTemplate?: (template: Template) => void;
  onViewTemplate?: (template: Template) => void;
}

export default function CuratedTemplatesSection({
  templates,
  onUseTemplate,
  onViewTemplate,
}: CuratedTemplatesSectionProps) {
  // No separate sections - return null to hide this component
  return null;
}
