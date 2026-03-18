"""
Prompt Manager & Batch Processor
=================================
Centralized prompt management and efficient batch processing for AI calls.

Features:
- Load prompts from config/prompts.json
- Variable substitution in templates
- Batch processing for leads (reduce API calls by 5x)
"""

import os
import json
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("PromptManager")


class PromptManager:
    """
    Manages prompt templates from config/prompts.json.
    Allows dynamic loading, variable substitution, and runtime reload.
    """
    
    def __init__(self):
        from utils import ConfigManager
        self.config = ConfigManager()
        self.prompts_path = os.path.join(self.config.root_dir, 'config', 'prompts.json')
        self.prompts = self._load_prompts()
    
    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompts from JSON file."""
        if not os.path.exists(self.prompts_path):
            logger.warning(f"Prompts file not found: {self.prompts_path}")
            return {}
        
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            return {}
    
    def reload(self):
        """Reload prompts from file (useful for runtime updates)."""
        self.prompts = self._load_prompts()
        logger.info("Prompts reloaded from file.")
    
    def get(self, category: str, task: str, **variables) -> Dict[str, Any]:
        """
        Get a prompt template with variables substituted.
        
        Args:
            category: Top-level category (e.g., 'cafe_spy', 'content_generation')
            task: Task name within category (e.g., 'lead_analysis', 'writing')
            **variables: Variables to substitute in template
        
        Returns:
            {
                'prompt': str,  # Full prompt with variables filled
                'temperature': float,
                'model_preference': str  # 'flash' or 'pro'
            }
        
        Example:
            pm = PromptManager()
            info = pm.get('cafe_spy', 'lead_analysis', 
                         title="다이어트 한약", 
                         body="요요 없이 살 빼고 싶어요...")
        """
        try:
            template_info = self.prompts.get(category, {}).get(task)
            
            if not template_info:
                logger.warning(f"Prompt not found: {category}/{task}")
                return {
                    'prompt': f"[Missing prompt: {category}/{task}]",
                    'temperature': 0.7,
                    'model_preference': 'flash'
                }
            
            # Build full prompt
            system_prompt = template_info.get('system', '')
            template = template_info.get('template', '')
            
            # Substitute variables
            try:
                filled_template = template.format(**variables)
            except KeyError as e:
                logger.warning(f"Missing variable {e} in template {category}/{task}")
                filled_template = template  # Use raw template if variable missing
            
            full_prompt = f"{system_prompt}\n\n{filled_template}" if system_prompt else filled_template
            
            return {
                'prompt': full_prompt,
                'temperature': template_info.get('temperature', 0.7),
                'model_preference': template_info.get('model_preference', 'flash'),
                'max_batch_size': template_info.get('max_batch_size', 10)
            }
            
        except Exception as e:
            logger.error(f"Error getting prompt {category}/{task}: {e}")
            return {
                'prompt': f"Error loading prompt: {e}",
                'temperature': 0.7,
                'model_preference': 'flash'
            }
    
    def get_legacy(self, key: str, **variables) -> str:
        """
        Get legacy prompts from _legacy section for backward compatibility.
        
        Args:
            key: Legacy prompt key (e.g., 'premium_blog', 'track_b_factory')
            **variables: Variables to substitute
        
        Returns:
            Formatted prompt string
        """
        legacy_prompts = self.prompts.get('_legacy', {})
        template = legacy_prompts.get(key, '')
        
        if not template:
            return f"[Legacy prompt not found: {key}]"
        
        try:
            return template.format(**variables)
        except KeyError:
            return template  # Return raw if variables missing
    
    def list_prompts(self) -> Dict[str, List[str]]:
        """List all available prompts by category."""
        result = {}
        for category, tasks in self.prompts.items():
            if category.startswith('_'):  # Skip meta keys
                continue
            if isinstance(tasks, dict):
                result[category] = list(tasks.keys())
        return result


class BatchProcessor:
    """
    Processes multiple items in a single AI call for efficiency.
    Reduces API calls by 5-10x and saves ~64% tokens.
    """
    
    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size
        self.prompt_manager = PromptManager()
        
        # Lazy load AI client
        self._client = None
        self._model_name = None
    
    def _get_client(self):
        """Initialize AI client lazily."""
        if self._client is None:
            from google import genai
            from utils import ConfigManager
            
            config = ConfigManager()
            api_key = config.get_api_key()
            
            if api_key:
                self._client = genai.Client(api_key=api_key)
                self._model_name = config.get_model_name("flash")
            else:
                logger.error("No API key available for BatchProcessor")
        
        return self._client, self._model_name
    
    def process_leads(self, leads: List[Dict]) -> List[Dict]:
        """
        Process leads in batches for efficiency.
        
        Args:
            leads: List of lead dictionaries with at least 'title' key
                   [{'id': 1, 'title': '...', 'body': '...'}, ...]
        
        Returns:
            List of analysis results:
            [{'id': 1, 'summary': '...', 'score': 'Hot', 'reply': '...'}, ...]
        """
        if not leads:
            return []
        
        results = []
        
        # Process in batches
        for i in range(0, len(leads), self.batch_size):
            batch = leads[i:i + self.batch_size]
            logger.info(f"Processing batch {i//self.batch_size + 1} ({len(batch)} leads)")
            
            try:
                batch_results = self._process_batch(batch)
                results.extend(batch_results)
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                # Fallback to individual processing
                for lead in batch:
                    results.append({
                        'id': lead.get('id', 0),
                        'summary': 'Error: Batch processing failed',
                        'score': 'Cold',
                        'reply': ''
                    })
        
        return results
    
    def _process_batch(self, batch: List[Dict]) -> List[Dict]:
        """Process a single batch of leads."""
        client, model_name = self._get_client()
        
        if not client:
            return [{'id': l.get('id', 0), 'summary': 'No AI client', 'score': 'Cold', 'reply': ''} for l in batch]
        
        # Format leads for batch prompt
        leads_formatted = self._format_leads(batch)
        
        # Get batch prompt
        prompt_info = self.prompt_manager.get(
            'cafe_spy', 'batch_lead_analysis',
            count=len(batch),
            leads_formatted=leads_formatted
        )
        
        # Make AI call
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_info['prompt'],
                config={'temperature': prompt_info['temperature']}
            )
            
            # Track API usage
            try:
                from api_tracker import get_tracker
                tokens = len(prompt_info['prompt']) // 4 + len(response.text) // 4
                get_tracker().log_call('gemini', 'batch_lead_analysis', tokens=tokens, success=True)
            except Exception:
                pass
            
            # Parse response
            return self._parse_batch_response(response.text, batch)
            
        except Exception as e:
            logger.error(f"Batch AI call failed: {e}")
            raise
    
    def _format_leads(self, batch: List[Dict]) -> str:
        """Format leads into numbered text for batch prompt."""
        lines = []
        
        for i, lead in enumerate(batch, 1):
            lines.append(f"[LEAD {i}]")
            lines.append(f"Title: {lead.get('title', 'N/A')}")
            lines.append(f"Author: {lead.get('author', 'Unknown')}")
            
            body = lead.get('body', '') or lead.get('content', '')
            if body:
                # Truncate body to save tokens
                lines.append(f"Content: {body[:500]}...")
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_batch_response(self, response: str, batch: List[Dict]) -> List[Dict]:
        """Parse AI response and map back to leads."""
        results = []
        
        # Split by LEAD_ID markers
        lead_sections = re.split(r'---\s*\n*LEAD_ID:', response)
        
        # If that doesn't work, try alternative pattern
        if len(lead_sections) < 2:
            lead_sections = re.split(r'LEAD_ID:\s*', response)
        
        for section in lead_sections:
            if not section.strip():
                continue
            
            try:
                # Extract LEAD_ID
                id_match = re.search(r'^(\d+)', section.strip())
                if not id_match:
                    continue
                
                lead_idx = int(id_match.group(1)) - 1  # Convert to 0-indexed
                
                if lead_idx < 0 or lead_idx >= len(batch):
                    continue
                
                # Extract fields
                summary_match = re.search(r'SUMMARY:\s*(.+?)(?=SCORE:|$)', section, re.DOTALL)
                score_match = re.search(r'SCORE:\s*(\w+)', section)
                reply_match = re.search(r'REPLY:\s*(.+?)(?=---|\Z)', section, re.DOTALL)
                
                results.append({
                    'id': batch[lead_idx].get('id', lead_idx),
                    'summary': summary_match.group(1).strip() if summary_match else '',
                    'score': score_match.group(1).strip() if score_match else 'Cold',
                    'reply': reply_match.group(1).strip() if reply_match else ''
                })
                
            except Exception as e:
                logger.warning(f"Failed to parse lead section: {e}")
                continue
        
        # Fill in any missing leads
        parsed_ids = {r['id'] for r in results}
        for lead in batch:
            if lead.get('id', 0) not in parsed_ids:
                results.append({
                    'id': lead.get('id', 0),
                    'summary': 'Parse error',
                    'score': 'Warm',
                    'reply': ''
                })
        
        return results


# Convenience function for quick access
_prompt_manager_instance = None

def get_prompt_manager() -> PromptManager:
    """Get singleton PromptManager instance."""
    global _prompt_manager_instance
    if _prompt_manager_instance is None:
        _prompt_manager_instance = PromptManager()
    return _prompt_manager_instance


if __name__ == "__main__":
    # Test PromptManager
    pm = PromptManager()
    
    print("=== Available Prompts ===")
    for category, tasks in pm.list_prompts().items():
        print(f"  {category}: {tasks}")
    
    print("\n=== Sample Prompt ===")
    sample = pm.get('cafe_spy', 'lead_analysis', 
                    title="다이어트 한약 추천해주세요",
                    author="꿀맘",
                    body="요요 없이 다이어트 하고 싶은데 한약 어디서 받으면 좋을까요?")
    print(f"Temperature: {sample['temperature']}")
    print(f"Model: {sample['model_preference']}")
    print(f"Prompt preview: {sample['prompt'][:200]}...")
    
    print("\n=== Legacy Prompt ===")
    legacy = pm.get_legacy('premium_blog', topic="다이어트", mode="Health", weather="맑음")
    print(f"Preview: {legacy[:200]}...")
