from tinycss.page3 import CSSPage3Parser
import css_properties
from css_options import css_opts
from validations import ValidationHelpersMixin


DEBUG = True if __name__ == '__main__' else False


class MissingTokenType(Exception):
    def __init__(self):
        print('Invalid token type: please add a '
              'new one to the token types config.')


class MissingAtKeywordType(Exception):
    def __init__(self):
        print('Invalid @ keyword type. Options are: {}'.format(
            ' ').join(css_opts['at_types']))


class InputBuilder(ValidationHelpersMixin, CSSPage3Parser):
    """
    Convention: all public methods return `self` to allow for chaining.
    TODO: docs, docstrings
    """

    def __init__(
            self, data, unwanted_props=[],
            css_input_wrapper_class='css-func',
            custom_input_html=None, show_empty=False, use_bytes=False):
        self.use_value = True
        self._generated_data = None
        self.css_input_wrapper_class = css_input_wrapper_class
        self.unwanted_props = unwanted_props
        self.show_empty_declarations = show_empty
        self.custom_input_html = custom_input_html
        if use_bytes:
            self.stylesheet = self.parse_stylesheet_bytes(data)
        else:
            self.stylesheet = self.parse_stylesheet_file(data)
        self.animation_group_html = ('<div class="animation-group">'
                                     '{percentages}</div>')
        self.surrounding_html = '<div class="{}">{}</div>'
        self.container_html = ('<div class="selector-group">\n'
                               '<span class="selector-label">'
                               '{selector}</span> {}\n{code}{}</div>\n')
        self.default_input_html = ('<label>\n<em>{name}:</em>'
                                   '\n{input_html}\n</label>\n')

    def parse_media(self, tokens):
        """Private method overridden from tinycss."""
        mediaquery_tokens = [f for f in tokens if f.type == 'IDENT']
        return mediaquery_tokens

    def parse_at_rule(self, rule, previous_rules, errors, context):
        """Inject a custom property for filtering purposes.
        This method overrides the private tinycss method."""
        if rule.at_keyword == '@keyframes':
            rule.keyframes = True
            return rule
        # Parse the rest normally
        return super(InputBuilder, self).parse_at_rule(
            rule, previous_rules, errors, context)

    def _strip_quotes(self, val):
        """Normalize properties with beginning or
        trailing quotations, like `content: ""`
        """
        if type(val) != 'str':
            return val
        if val.startswith('"'):
            val = val[1:]
        if val.endswith('"'):
            val = val[:-1]
        return val

    def _convert_odd_types(self, value):
        try:
            return css_opts['odd_props'][value]
        except KeyError:
            return None

    def _get_dropdown_html(self, props, name='', token=None):
        """Takes name and value, then builds
        matching select > option html"""
        # Accompanying input html required for some
        # non-dropdown complementary fields
        non_dropdown_html = ''
        dropdown_html = '<select name="{}">'.format(name)
        for prop in props:
            # One off cases where some value should be represented
            # by a different field type
            if prop in css_opts['odd_props']:
                new_token_type = self._convert_odd_types(prop)
                if new_token_type is not None:
                    non_dropdown_html += self._get_input_html(
                        None,
                        new_token_type, prop, prop)
            else:
                # Build the /actual/ option html.
                dropdown_html += self._get_input_html(
                    None,
                    'OPTION', prop, prop, selected='')
        dropdown_html += '</select>'
        return (non_dropdown_html + (
            '<em class="or-divider">or</em>'
            if non_dropdown_html else '') + dropdown_html)

    def _is_cruft(self, token_type):
        if token_type in ['S', 'DELIM']:
            return True
        return False

    def _get_input_html(self, selector, token_type, name, value, **kwargs):
        if self._is_cruft(token_type):
            return ''
        value = self._strip_quotes(value)
        try:
            # Plain ol' direct mapping
            return css_opts['types'][token_type].format(
                name='{}[{}]'.format(selector, name), placeholder=value,
                value=value if self.use_value else '', **kwargs)
        except KeyError:
            raise MissingTokenType

    def _wrap_input_html(self, **kwargs):
        """Wraps form field grouping with surrounding html"""
        # Allow arbitrary custom html, so long as the kwargs
        # match up the format kwargs -- otherwise error will be thrown.
        wrapper = (self.custom_input_html if self.custom_input_html
                   else self.default_input_html)
        html = wrapper.format(**kwargs)
        return self.surrounding_html.format(self.css_input_wrapper_class, html)

    def _get_new_type(self, css):
        if self._is_hex(css):
            return 'HASH'
        elif self._is_percentage(css):
            return 'PERCENTAGE'
        elif self._is_float(css):
            return 'FLOAT'
        elif self._is_int(css):
            return 'INTEGER'
        else:
            return 'IDENT'

    def _get_token_value(self, token):
        try:
            token_value = token.value
        except AttributeError:
            token_value = token.function_name
        return token_value

    def _get_form_html_data(
            self, selector, token, prop_name, priority=None, shorthand=False):
        """Generates form html to be used by html builder"""
        if self._is_cruft(token.type):
            return ''
        token_value = self._get_token_value(token)
        # Normalize single vs multiple valued declarations
        try:
            prop_key = css_properties.rules[prop_name]
            # Only overwrite string if it's not container type
            if not shorthand and prop_key['dropdown']:
                html = self._get_dropdown_html(
                    prop_key['values'], name=prop_name, token=token.type)
            else:
                html = self._get_input_html(
                    selector, token.type, prop_name, token_value)
        except KeyError:
            if DEBUG:
                print('[ERROR] Property: "{}"'.format(prop_name))
            # Try to recover gracefully with the appropriate type
            _css = token.as_css()
            new_type = self._get_new_type(_css)
            html = self._get_input_html(
                selector, new_type, prop_name, token_value)
        if priority:
            html += '<label>Important? {}</label>'.format(self._get_input_html(
                selector, 'BOOLEAN', 'important', 'important',
                checked='checked'))
        return html

    def _get_at_keyword_type(self, ruleset):
        keys = ruleset.keys()
        if 'uri' in keys or 'media' in keys:
            return 'import'
        if 'rules' in keys:
            return 'media'
        if 'keyframes' in keys:
            return 'keyframes'
        if 'at_keyword' in keys:
            return ruleset['at_keyword'].replace('@', '')
        raise MissingAtKeywordType

    def _group_keyframe_tokens(self, tokens):
        """Groups a list of tokens from tinycss by brackets and contained css.
        Since all tokens come in as one list, we need to group by individual
        percentage declarations to allow differentiating between groups.
            @keyframes myanimation {
                10%, 20% {}
                50, 60% {}
                100% {}
            }
        """
        token_groups = {}
        current_group = 0
        for token in tokens:
            # Skip some pieces that are unnecessary,
            # like empty strings or commas/fragments
            if token.as_css()[0] not in [',', ' ']:
                try:
                    if token.as_css().startswith('{'):
                        token_groups[current_group]['rules'].append(token)
                    else:
                        token_groups[current_group]['percentages'].append(token)
                except KeyError:
                    token_groups[current_group] = {
                        'percentages': [],
                        'rules': []
                    }
            # Move to the next set of declarations
            if token.as_css().startswith('{'):
                current_group += 1
        return token_groups

    def _generate_keyframes_declarations(self, ruleset):
        inputs = []
        junk_types = ['DELIM', 'S', ':', ';']
        token_groups = self._group_keyframe_tokens(ruleset.body)
        for _, token_group in token_groups.iteritems():
            for token in token_group['rules']:
                percentages = ', '.join(
                    [t.as_css() for t in token_group['percentages']])
                # All tokens are container tokens
                if hasattr(token, 'is_container'):
                    # Parse container tokens
                    sub_tokens = [t for t in token.content if t.type
                                  not in junk_types]
                    for key, sub_token in enumerate(sub_tokens):
                        if not self._is_valid_css_declaration(
                                sub_token.as_css()):
                            continue
                        if sub_token.type == 'FUNCTION':
                            function_tokens = [t for t in sub_token.content
                                               if t.type not in junk_types]
                            for k, function_token in enumerate(function_tokens):
                                label = '{} ({})'.format(
                                    sub_token.function_name, k)
                                name = '{}_{}'.format(
                                    sub_token.function_name, k)
                                input_html = self._get_input_html(
                                    label,
                                    function_token.type, name,
                                    function_token.as_css())
                                kwargs = {
                                    'name': label,
                                    'value': function_token.as_css(),
                                    'input_html': input_html
                                }
                                inputs.append(self._wrap_input_html(**kwargs))
                        else:
                            html = ''
                            # Show, but don't create a field for
                            # percentage groupings
                            if sub_token.type == 'IDENT':
                                input_html = ''
                            else:
                                input_html = self._get_input_html(
                                    label,
                                    sub_token.type,
                                    self._get_token_value(sub_token),
                                    sub_token.as_css())
                            kwargs = {
                                'name': self._get_token_value(sub_token),
                                'value': sub_token.as_css(),
                                'input_html': input_html
                            }
                            # Only show the percentage label once per group
                            if key == 2:
                                group_html = self.animation_group_html.format(
                                    percentages=percentages)
                            else:
                                group_html = ''
                            html += '{} {}'.format(
                                group_html, self._wrap_input_html(**kwargs))
                            inputs.append(html)
        return inputs

    def _generate_mediaquery_declarations(self, ruleset):
        inputs = []
        for rule in ruleset.rules:
            sub_inputs = self._generate_regular_declarations(rule)
            # Re-build parsed selector
            selector = ''.join([s.value for s in rule.selector])
            kwargs = {
                'name': selector,
                'input_html': ''.join(sub_inputs)
            }
            # Process all sub rules for every individual "parent" media rule.
            inputs.append(self._wrap_input_html(**kwargs))
        return inputs

    def _generate_import_declarations(self, ruleset):
        inputs, name = [], 'url ({})'.format(ruleset.uri)
        input_html = self._get_input_html(name, 'URI', ('import-url'), name)
        kwargs = {
            'name': name,
            'value': name,
            'input_html': input_html
        }
        inputs.append(self._wrap_input_html(**kwargs))
        return inputs

    def _generate_regular_declarations(self, ruleset):
        inputs = []
        # All declarations in the selector
        for declaration in ruleset.declarations:
            # Property, e.g. background-color
            prop_name = declaration.name
            if self._is_valid_css_declaration(prop_name):
                priority = declaration.priority
                is_shorthand = prop_name in css_opts['shorthand']
                # if is_shorthand and prop_name
                html = ''
                # Declaration tokens, e.g. "[2px, solid, #4444]"
                for token in declaration.value:
                    if self._is_cruft(token.type):
                        continue
                    if hasattr(token, 'function_name'):
                        # Update prop_name to add function for more context
                        prop_name = '{} ({})'.format(
                            prop_name, token.function_name)
                        if not self._is_valid_css_declaration(
                                token.function_name):
                            continue
                        if token.function_name in css_opts['pseudo_shorthand']:
                            is_shorthand = True
                    if hasattr(token, 'content'):
                        for sub_token in token.content:
                            html += self._get_form_html_data(
                                ruleset.selector.as_css(),
                                sub_token, prop_name, priority=priority,
                                shorthand=is_shorthand)
                    else:
                        if is_shorthand:
                            # Note: shorthand properties are not grouped
                            # with appropriate dropdowns
                            # like single declarations, but rather, are
                            # converted to plain text inputs.
                            html += self._get_input_html(
                                ruleset.selector.as_css(),
                                token.type, token.unit,
                                self._get_token_value(token))
                        else:
                            html = self._get_form_html_data(
                                ruleset.selector.as_css(),
                                token, prop_name, priority=priority,
                                shorthand=is_shorthand)
                # Add the final rendered html + labels, etc
                # Only append properties that could be
                # rendered as form fields
                if html or self.show_empty_declarations:
                    inputs.append(
                        self._wrap_input_html(
                            **{'name': prop_name, 'input_html': html}))
        return inputs

    def _get_generator(self, ruleset, at_keyword=False):
        if at_keyword:
            # e.g. @import url('foo.css') projection, tv;
            group_label = '@' + self._get_at_keyword_type(ruleset)
            # Drill down further to determine the @ keyword type
            try:
                label_map = {
                    '@import': self._generate_import_declarations,
                    '@media': self._generate_mediaquery_declarations,
                    '@keyframes': self._generate_keyframes_declarations
                }
                active_func = label_map[group_label]
            except KeyError:
                raise MissingAtKeywordType
            # Customize group label for keyframes
            if group_label == '@keyframes':
                group_label += ' ' + ruleset.head[0].as_css()
        else:
            # The group or single selector:
            # .foo, .bar, .foo.bar {}
            group_label = ruleset.selector.as_css()
            active_func = self._generate_regular_declarations
        return group_label, active_func

    def generate(self):
        """Generates all html from the available stylesheet
        reference exposed by init function."""
        html_inputs = []
        for ruleset in self.stylesheet.rules:
            group_label = None
            is_at_keyword = ruleset.at_keyword is not None
            group_label, active_func = self._get_generator(
                ruleset, at_keyword=is_at_keyword)
            input_html = active_func(ruleset)
            selector = ', <br>'.join(group_label.split(','))
            code = ' '.join(input_html)
            html_inputs.append(
                self.container_html.format(
                    '{', '}', selector=selector, code=code))
        # Join all data and populate global property
        self._generated_data = ''.join(html_inputs)
        return self

    def save(self, filename):
        if self._generated_data is None:
            print('No data has been generated yet!')
            return
        with open(filename, 'w') as newfile:
            newfile.write(self._generated_data)
            newfile.write('\n')
            newfile.close()
