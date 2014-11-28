import random, time
from django.db import models
from django.conf import settings
from django.utils.text import slugify

from smartfields.models.fields.dependencies import Dependency, ForwardDependency
from smartfields.models.fields.managers import FieldManager
from smartfields.processors.html import HTMLSanitizer, HTMLStripper


class Field(models.Field):
    FAIL_SILENTLY = getattr(settings, 'SMARTFIELDS_FAIL_SILENTLY', True)
    manager = None
    manager_class = FieldManager
    
    def __init__(self, dependencies=None, manager_class=None, processor_class=None, 
                 *args, **kwargs):
        if manager_class is not None:
            self.manager_class = manager_class
        self.manager = self.manager_class(
            self, dependencies=dependencies, processor_class=processor_class)
        super(Field, self).__init__(*args, **kwargs)


    def contribute_to_class(self, cls, name):
        if not hasattr(cls, 'smartfields_managers') or cls.smartfields_managers is None:
            cls.smartfields_managers = []
        cls.smartfields_managers.append(self.manager)
        super(Field, self).contribute_to_class(cls, name)


    def get_status(self, instance):
        current_status = {
            'app_label': instance._meta.app_label,
            'model_name': instance._meta.model_name,
            'pk': instance.pk,
            'field_name': self.name,
            'state': 'ready'
        }
        status = self.manager.get_status(instance)
        if status is not None:
            current_status.update(status)
        return current_status




class SlugField(Field, models.SlugField):

    @staticmethod
    def generate_slug(instance, field, value):
        current_value = getattr(instance, field.name)
        if not current_value and value:
            slug = slugify(value)[:field.max_length]
            if field._unique:
                manager = instance.__class__._default_manager
                unique_slug = slug
                existing = manager.filter(**{'%s__iexact' % field.name: unique_slug})
                # making sure slug is unique by adding a random number
                while existing.exists():
                    r_str = str(random.randint(0, int(time.time())))
                    l = field.max_length - (len(slug) + len(r_str) + 1)
                    l_slug = slug[:l] if l < 0 else slug
                    unique_slug = "%s-%s" % (l_slug, r_str)
                    existing = manager.filter(**{'%s__iexact' % field.name: unique_slug})
                slug = unique_slug
            return slug
        return current_value


    def __init__(self, default_dependency=None, dependencies=None, *args, **kwargs):
        dependencies = dependencies or []
        if default_dependency is not None:
            dependencies.append(Dependency(
                dependency=default_dependency, handler=self.generate_slug))
        super(SlugField, self).__init__(dependencies=dependencies, *args, **kwargs)


class HTMLField(Field, models.TextField):

    def __init__(self, sanitize=True, no_html_field=None, dependencies=None, *args, **kwargs):
        """:keyword bool sanitize: if set to `True` creaters a self dependency,
        that removes unwanted tags and attributes, which are specified and
        handled by :class:`HTMLSanitizer`. Default: `True`

        :keyword str no_html_field: field name, which will hold the HTML
        stripped value of this field.

        """
        dependencies = dependencies or []
        if sanitize:
            sanitizer_class = kwargs.pop('sanitizer_class', HTMLSanitizer)
            dependencies.append(Dependency(
                processor_class=sanitizer_class, persistent=False))
        if no_html_field is not None:
            dependencies.append(ForwardDependency(
                no_html_field, processor_class=HTMLStripper, persistent=False))
        super(HTMLField, self).__init__(dependencies=dependencies, *args, **kwargs)


    def save_form_data(self, instance, data):
        super(HTMLField, self).save_form_data(instance, data)
        if self.manager is not None:
            self.manager.update(instance)