export const ChatTitlePrompt =
`
<instructions>
  Analyze the chat history and output only a concise title.
  Match the conversation language. Use 3-5 English words or an equivalent length in other languages.
</instructions>

<chat_history>
  {%- for message in messages %}
  <message role="{{ message.type }}">{{ message.text }}</message>
  {%- endfor %}
</chat_history>
`

export const PluginsPromptTemplate =
`<plugins>
{%- for plugin in plugins %}
<plugin id="{{ plugin.id }}">
{%- if plugin.prompt %}
<plugin_prompt>
{{ plugin.prompt }}
</plugin_prompt>
{%- endif %}
</plugin>
{%- endfor %}
</plugins>
`

export const DefaultPromptTemplate =
`{%- if _rolePrompt %}
<role_prompt>
{{ _rolePrompt }}
</role_prompt>
{%- endif %}

{{ _pluginsPrompt }}
`
